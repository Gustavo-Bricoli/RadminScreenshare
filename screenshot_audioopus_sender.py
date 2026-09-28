import os
import socket
import struct
import time
import threading
from fractions import Fraction

import av
import mss
import numpy as np
import soundcard as sc


if os.name == "nt":

    opus_directories = [
        os.path.dirname(os.path.abspath(__file__)),
        os.environ.get("OPUS_DLL_DIR", ""),
        r"C:\Program Files\Audacity"
    ]

    for opus_directory in opus_directories:

        if os.path.isfile(
            os.path.join(opus_directory, "opus.dll")
        ):

            os.environ["PATH"] = (
                opus_directory
                + os.pathsep
                + os.environ.get("PATH", "")
            )

            break

from opuslib import Encoder


# ============================================================
# CONFIGURATION
# ============================================================

HOST = "0.0.0.0"

VIDEO_PORT = 5000
AUDIO_PORT = 5001
VIDEO_CHUNK_SIZE = 1200
FULL_REFRESH_SECONDS = 1

FPS = 30
VIDEO_BITRATE = "5M"
MONITOR = 1

AUDIO_SAMPLE_RATE = 48000
AUDIO_CHANNELS = 2

# Opus accepts specific frame sizes.
# 960 samples at 48 kHz = 20 ms.
AUDIO_FRAME_SIZE = 960
AUDIO_CAPTURE_FRAMES = AUDIO_FRAME_SIZE * 4

OPUS_BITRATE = 128000


# ============================================================
# VIDEO UDP PACKETS
# ============================================================

def send_video_frame(sock, address, frame_id, frame, is_keyframe):

    chunk_count = (
        len(frame) + VIDEO_CHUNK_SIZE - 1
    ) // VIDEO_CHUNK_SIZE

    for chunk_id in range(chunk_count):

        start = chunk_id * VIDEO_CHUNK_SIZE
        end = start + VIDEO_CHUNK_SIZE

        packet = struct.pack(
            "!IHHB",
            frame_id,
            chunk_id,
            chunk_count,
            int(is_keyframe)
        ) + frame[start:end]

        sock.sendto(packet, address)


# ============================================================
# VIDEO SERVER
# ============================================================

def video_server():

    print("[VIDEO] Starting server...")

    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    server.bind((HOST, VIDEO_PORT))

    print(
        f"[VIDEO] Waiting for viewer "
        f"on UDP port {VIDEO_PORT}..."
    )

    while True:

        data, viewer_address = server.recvfrom(1024)

        if data == b"VIDEO_HELLO":
            break

    print(
        f"[VIDEO] Viewer connected: "
        f"{viewer_address}"
    )

    with mss.MSS() as sct:

        monitor = sct.monitors[MONITOR]
        encoder = None

        try:

            frame_interval = 1 / FPS
            frame_id = 0

            while True:

                start = time.perf_counter()

                # Capture screen
                screenshot = sct.grab(
                    monitor
                )

                width, height = screenshot.size

                if encoder is None:

                    encoder = av.CodecContext.create(
                        "libx264",
                        "w"
                    )

                    encoder.width = width
                    encoder.height = height
                    encoder.pix_fmt = "yuv420p"
                    encoder.time_base = Fraction(1, FPS)
                    encoder.framerate = Fraction(FPS, 1)
                    encoder.bit_rate = 5_000_000
                    encoder.options = {
                        "preset": "ultrafast",
                        "tune": "zerolatency",
                        "g": str(FPS * FULL_REFRESH_SECONDS),
                        "keyint_min": str(FPS * FULL_REFRESH_SECONDS),
                        "forced-idr": "1",
                        "sc_threshold": "0",
                        "bframes": "0",
                        "rc-lookahead": "0",
                        "threads": "1"
                    }

                    encoder.open()

                image = np.frombuffer(
                    screenshot.rgb,
                    dtype=np.uint8
                ).reshape(
                    (height, width, 3)
                )

                video_frame = av.VideoFrame.from_ndarray(
                    image,
                    format="rgb24"
                )

                video_frame.pts = frame_id

                for encoded_packet in encoder.encode(video_frame):

                    send_video_frame(
                        server,
                        viewer_address,
                        frame_id,
                        bytes(encoded_packet),
                        encoded_packet.is_keyframe
                    )

                frame_id = (frame_id + 1) & 0xFFFFFFFF

                # Maintain approximately 30 FPS
                elapsed = (
                    time.perf_counter()
                    - start
                )

                remaining = (
                    frame_interval
                    - elapsed
                )

                if remaining > 0:
                    time.sleep(remaining)

        except Exception as e:

            print(
                "[VIDEO] Error:",
                e
            )

        finally:

            server.close()


# ============================================================
# AUDIO SERVER
# ============================================================

def audio_server():

    print("[AUDIO] Starting server...")

    server = socket.socket(
        socket.AF_INET,
        socket.SOCK_DGRAM
    )

    server.setsockopt(
        socket.SOL_SOCKET,
        socket.SO_REUSEADDR,
        1
    )

    server.bind(
        (HOST, AUDIO_PORT)
    )

    print(
        f"[AUDIO] UDP audio ready "
        f"on port {AUDIO_PORT}."
    )

    print(
        "[AUDIO] Waiting for viewer..."
    )

    # Default Windows output device
    speaker = sc.default_speaker()

    print(
        "[AUDIO] System audio device:"
    )

    print(
        "        ",
        speaker.name
    )

    # Windows loopback capture
    microphone = sc.get_microphone(
        speaker.name,
        include_loopback=True
    )

    # Opus encoder
    encoder = Encoder(
        AUDIO_SAMPLE_RATE,
        AUDIO_CHANNELS,
        "audio"
    )

    encoder.bitrate = OPUS_BITRATE

    # We don't know the viewer's IP yet.
    # The viewer sends a small "hello" packet first.
    viewer_address = None

    sequence = 0
    audio_frames = 0

    # --------------------------------------------------------
    # Wait for viewer
    # --------------------------------------------------------

    while viewer_address is None:

        try:

            server.settimeout(1.0)

            data, address = server.recvfrom(1024)

            if data == b"AUDIO_HELLO":

                viewer_address = address

                print(
                    f"[AUDIO] Viewer connected: "
                    f"{address}"
                )

        except socket.timeout:

            continue

    server.settimeout(None)

    # --------------------------------------------------------
    # Capture system audio
    # --------------------------------------------------------

    try:

        with microphone.recorder(
            samplerate=AUDIO_SAMPLE_RATE,
            channels=AUDIO_CHANNELS,
            blocksize=AUDIO_CAPTURE_FRAMES
        ) as recorder:

            while True:

                # Capture several Opus frames at once. This gives the
                # Windows loopback recorder more scheduling headroom.
                captured_audio = recorder.record(
                    numframes=AUDIO_CAPTURE_FRAMES
                )

                captured_audio = np.asarray(
                    captured_audio,
                    dtype=np.float32
                )

                # Make sure we have the expected shape
                if captured_audio.ndim == 1:

                    captured_audio = captured_audio.reshape(
                        (-1, AUDIO_CHANNELS)
                    )

                for offset in range(
                    0,
                    len(captured_audio),
                    AUDIO_FRAME_SIZE
                ):

                    audio = captured_audio[
                        offset:offset + AUDIO_FRAME_SIZE
                    ]

                    if len(audio) != AUDIO_FRAME_SIZE:
                        continue

                    # Opus expects signed 16-bit PCM
                    pcm = np.clip(
                        audio * 32767,
                        -32768,
                        32767
                    ).astype(
                        np.int16
                    )

                    encoded = encoder.encode(
                        pcm.tobytes(),
                        AUDIO_FRAME_SIZE
                    )

                    packet = struct.pack(
                        "!I",
                        sequence
                    ) + encoded

                    server.sendto(
                        packet,
                        viewer_address
                    )

                    audio_frames += 1

                    if audio_frames % 50 == 0:

                        print(
                            f"[AUDIO] Sent {audio_frames} frames; "
                            f"level={float(np.max(np.abs(audio))):.5f}"
                        )

                    sequence = (
                        sequence + 1
                    ) & 0xFFFFFFFF

    except Exception as e:

        print(
            "[AUDIO] Error:",
            e
        )

    finally:

        server.close()


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 55)

    print(
        "          SCREEN + AUDIO SERVER"
    )

    print("=" * 55)

    print()

    print(
        f"Video: TCP {VIDEO_PORT}"
    )

    print(
        f"Audio: UDP {AUDIO_PORT}"
    )

    print(
        f"Video: {FPS} FPS"
    )

    print(
        f"Audio: Opus {OPUS_BITRATE // 1000} kbps"
    )

    print()

    video_thread = threading.Thread(
        target=video_server,
        daemon=True
    )

    audio_thread = threading.Thread(
        target=audio_server,
        daemon=True
    )

    video_thread.start()
    audio_thread.start()

    try:

        while True:
            time.sleep(1)

    except KeyboardInterrupt:

        print()
        print(
            "Stopping server..."
        )


if __name__ == "__main__":
    main()