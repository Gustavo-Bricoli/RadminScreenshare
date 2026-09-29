import asyncio
import json
import os
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
AUDIO_FRAME_SIZE = 960


def get_publisher_token():
    query = urlencode({
        "room": ROOM,
        "identity": IDENTITY,
        "role": "publisher"
    })
    with urlopen(f"{TOKEN_URL}?{query}", timeout=10) as response:
        return json.load(response)


async def publish_video(source):
    interval = 1 / VIDEO_FPS
    next_frame = time.perf_counter()

    with mss.MSS() as capture:
        monitor = capture.monitors[VIDEO_MONITOR]

        while True:
            screenshot = capture.grab(monitor)
            width, height = screenshot.size
            frame = rtc.VideoFrame(
                width,
                height,
                rtc.VideoBufferType.RGB24,
                screenshot.rgb
            )
            source.capture_frame(frame)
            next_frame += interval
            await asyncio.sleep(
                max(0, next_frame - time.perf_counter())
            )


async def publish_audio(source):
    speaker = sc.default_speaker()
    microphone = sc.get_microphone(
        speaker.name,
        include_loopback=True
    )

    with microphone.recorder(
        samplerate=AUDIO_SAMPLE_RATE,
        channels=AUDIO_CHANNELS,
        blocksize=AUDIO_FRAME_SIZE
    ) as recorder:

        while True:
            audio = np.asarray(
                recorder.record(numframes=AUDIO_FRAME_SIZE),
                dtype=np.float32
            )

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
                    AUDIO_FRAME_SIZE
                )
            )
            await asyncio.sleep(0)


async def main():
    token_data = get_publisher_token()
    room = rtc.Room()
    await room.connect(token_data["url"], token_data["token"])

    with mss.MSS() as capture:
        width, height = capture.monitors[VIDEO_MONITOR]["width"], capture.monitors[VIDEO_MONITOR]["height"]

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

    await room.local_participant.publish_track(
        video_track,
        rtc.TrackPublishOptions(
            source=rtc.TrackSource.SOURCE_SCREENSHARE
        )
    )
    await room.local_participant.publish_track(
        audio_track,
        rtc.TrackPublishOptions(
            source=rtc.TrackSource.SOURCE_SCREENSHARE_AUDIO
        )
    )

    print(f"[WEBRTC] Published room={ROOM} identity={IDENTITY}")
    await asyncio.gather(
        publish_video(video_source),
        publish_audio(audio_source)
    )


if __name__ == "__main__":
    asyncio.run(main())