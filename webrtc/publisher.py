import asyncio
import json
import logging
import os
import queue
import threading
import time
from urllib.parse import urlencode
from urllib.request import urlopen

import mss
import numpy as np
import soundcard as sc
from livekit import rtc


ROOM = os.environ.get("LIVEKIT_ROOM", "screen-share")
IDENTITY = os.environ.get("LIVEKIT_IDENTITY", "python-sender")
TOKEN_URL = os.environ.get(
    "LIVEKIT_TOKEN_URL",
    "http://localhost:8787/api/token"
)
VIDEO_FPS = int(os.environ.get("LIVEKIT_VIDEO_FPS", "30"))
VIDEO_MONITOR = int(os.environ.get("LIVEKIT_MONITOR", "1"))
AUDIO_SAMPLE_RATE = 48000
AUDIO_CHANNELS = 2
AUDIO_CAPTURE_BUFFER_SIZE = int(
    os.environ.get("LIVEKIT_AUDIO_CAPTURE_BUFFER_SIZE", "4800")
)
AUDIO_QUEUE_SIZE = 5
logger = logging.getLogger("webrtc.publisher")


def get_publisher_token():
    query = urlencode({
        "room": ROOM,
        "identity": IDENTITY,
        "role": "publisher"
    })
    with urlopen(f"{TOKEN_URL}?{query}", timeout=10) as response:
        return json.load(response)


def set_task_error(error_future, error):
    if not error_future.done():
        error_future.set_exception(error)


def capture_video(source, stop_event, loop, error_future):
    interval = 1 / VIDEO_FPS
    next_frame = time.perf_counter()

    try:
        with mss.MSS() as capture:
            monitor = capture.monitors[VIDEO_MONITOR]
            first_frame = True

            while not stop_event.is_set():
                screenshot = capture.grab(monitor)
                width, height = screenshot.size
                frame = rtc.VideoFrame(
                    width,
                    height,
                    rtc.VideoBufferType.RGB24,
                    screenshot.rgb
                )
                source.capture_frame(frame)
                if first_frame:
                    logger.info("Screen capture started: %sx%s", width, height)
                    first_frame = False
                next_frame += interval
                stop_event.wait(
                    max(0, next_frame - time.perf_counter())
                )
    except Exception as error:
        logger.exception("Screen capture stopped after an error")
        loop.call_soon_threadsafe(set_task_error, error_future, error)


async def publish_video(source):
    loop = asyncio.get_running_loop()
    stop_event = threading.Event()
    error_future = loop.create_future()
    capture_thread = threading.Thread(
        target=capture_video,
        args=(source, stop_event, loop, error_future),
        name="screen-capture",
        daemon=True
    )
    capture_thread.start()

    try:
        await error_future
    finally:
        stop_event.set()
        await asyncio.to_thread(capture_thread.join)


async def send_audio_frame(source, audio):
    pcm = np.clip(
        audio * 32767,
        -32768,
        32767
    ).astype(np.int16)

    await source.capture_frame(
        rtc.AudioFrame(
            pcm.tobytes(),
            AUDIO_SAMPLE_RATE,
            AUDIO_CHANNELS,
            audio.shape[0]
        )
    )


def enqueue_audio(audio_queue, item):
    try:
        audio_queue.put_nowait(item)
        return False
    except queue.Full:
        try:
            audio_queue.get_nowait()
        except queue.Empty:
            pass
        audio_queue.put_nowait(item)
        return True


def capture_audio(audio_queue, stop_event):
    try:
        speaker = sc.default_speaker()
        logger.info(
            "System audio capture using speaker: %s (buffer=%s frames)",
            speaker.name,
            AUDIO_CAPTURE_BUFFER_SIZE
        )
        microphone = sc.get_microphone(
            speaker.name,
            include_loopback=True
        )

        with microphone.recorder(
            samplerate=AUDIO_SAMPLE_RATE,
            channels=AUDIO_CHANNELS,
            blocksize=AUDIO_CAPTURE_BUFFER_SIZE
        ) as recorder:
            last_audio_log = time.monotonic()
            block_duration = AUDIO_CAPTURE_BUFFER_SIZE / AUDIO_SAMPLE_RATE
            next_block_time = time.monotonic() + block_duration
            audio_squared_sum = 0.0
            audio_sample_count = 0
            audio_peak = 0.0
            dropped_audio_blocks = 0

            while not stop_event.is_set():
                audio = np.asarray(
                    recorder.record(numframes=AUDIO_CAPTURE_BUFFER_SIZE),
                    dtype=np.float32
                )

                audio_squared_sum += float(
                    np.sum(np.square(audio), dtype=np.float64)
                )
                audio_sample_count += audio.size
                audio_peak = max(audio_peak, float(np.max(np.abs(audio))))

                now = time.monotonic()
                if now - last_audio_log >= 5:
                    audio_rms = np.sqrt(
                        audio_squared_sum / max(audio_sample_count, 1)
                    )
                    logger.info(
                        "System audio capture level: rms=%.5f peak=%.5f dropped_blocks=%s",
                        audio_rms,
                        audio_peak,
                        dropped_audio_blocks
                    )
                    last_audio_log = now
                    audio_squared_sum = 0.0
                    audio_sample_count = 0
                    audio_peak = 0.0
                    dropped_audio_blocks = 0

                now = time.monotonic()
                if now < next_block_time:
                    stop_event.wait(next_block_time - now)
                    now = time.monotonic()
                next_block_time += block_duration
                if next_block_time < now:
                    next_block_time = now + block_duration

                if enqueue_audio(audio_queue, audio):
                    dropped_audio_blocks += 1
    except Exception as error:
        logger.exception("System audio capture stopped after an error")
        enqueue_audio(audio_queue, error)


async def publish_audio(source):
    stop_event = threading.Event()
    audio_queue = queue.Queue(maxsize=AUDIO_QUEUE_SIZE)
    capture_thread = threading.Thread(
        target=capture_audio,
        args=(audio_queue, stop_event),
        name="system-audio-capture",
        daemon=True
    )
    capture_thread.start()

    try:
        last_send_log = time.monotonic()
        sent_audio_blocks = 0
        total_send_duration = 0.0
        max_send_duration = 0.0

        while True:
            try:
                audio = await asyncio.to_thread(audio_queue.get, True, 0.2)
            except queue.Empty:
                continue
            if isinstance(audio, Exception):
                raise audio

            send_started = time.monotonic()
            await send_audio_frame(source, audio)
            send_duration = time.monotonic() - send_started
            sent_audio_blocks += 1
            total_send_duration += send_duration
            max_send_duration = max(max_send_duration, send_duration)

            now = time.monotonic()
            if now - last_send_log >= 5:
                logger.info(
                    "LiveKit audio send: blocks=%s avg=%.1fms max=%.1fms "
                    "source_queue=%.1fms capture_queue=%s",
                    sent_audio_blocks,
                    total_send_duration / sent_audio_blocks * 1000,
                    max_send_duration * 1000,
                    source.queued_duration * 1000,
                    audio_queue.qsize()
                )
                last_send_log = now
                sent_audio_blocks = 0
                total_send_duration = 0.0
                max_send_duration = 0.0
    finally:
        stop_event.set()
        await asyncio.to_thread(capture_thread.join)


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s"
    )
    logger.info("Requesting publisher token from %s", TOKEN_URL)
    token_data = get_publisher_token()
    logger.info(
        "Publisher token received: room=%s identity=%s livekit=%s",
        ROOM,
        IDENTITY,
        token_data["url"]
    )
    room = rtc.Room()
    tasks = []

    try:
        logger.info("Connecting publisher to LiveKit")
        await room.connect(token_data["url"], token_data["token"])
        logger.info("Publisher connected to LiveKit")

        with mss.MSS() as capture:
            width = capture.monitors[VIDEO_MONITOR]["width"]
            height = capture.monitors[VIDEO_MONITOR]["height"]

        video_source = rtc.VideoSource(
            width,
            height,
            is_screencast=True
        )
        audio_source = rtc.AudioSource(
            AUDIO_SAMPLE_RATE,
            AUDIO_CHANNELS
        )

        video_track = rtc.LocalVideoTrack.create_video_track(
            "screen",
            video_source
        )
        audio_track = rtc.LocalAudioTrack.create_audio_track(
            "system-audio",
            audio_source
        )

        video_publication = await room.local_participant.publish_track(
            video_track,
            rtc.TrackPublishOptions(
                source=rtc.TrackSource.SOURCE_SCREENSHARE
            )
        )
        logger.info("Screen track published: sid=%s", video_publication.sid)
        audio_publication = await room.local_participant.publish_track(
            audio_track,
            rtc.TrackPublishOptions(
                source=rtc.TrackSource.SOURCE_SCREENSHARE_AUDIO
            )
        )
        logger.info("System audio track published: sid=%s", audio_publication.sid)

        tasks = [
            asyncio.create_task(publish_video(video_source)),
            asyncio.create_task(publish_audio(audio_source))
        ]
        await asyncio.gather(*tasks)
    except Exception:
        logger.exception("Publisher stopped after an error")
        raise
    finally:
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await room.disconnect()


if __name__ == "__main__":
    asyncio.run(main())