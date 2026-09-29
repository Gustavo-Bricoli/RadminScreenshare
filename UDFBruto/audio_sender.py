import socket

import numpy as np
import soundcard as sc

from UDFBruto.screen_config import (
    AUDIO_CHANNELS,
    AUDIO_CAPTURE_FRAMES,
    AUDIO_FRAME_SIZE,
    AUDIO_PORT,
    AUDIO_SAMPLE_RATE,
    HOST,
    OPUS_BITRATE
)
from UDFBruto.media_protocol import encode_audio_packet, wait_for_hello


def run_audio_server():

    from UDFBruto.screen_config import configure_opus_library
    configure_opus_library()

    from opuslib import Encoder

    print("[AUDIO] Starting server...")
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, AUDIO_PORT))

    print(f"[AUDIO] UDP audio ready on port {AUDIO_PORT}.")
    print("[AUDIO] Waiting for viewer...")

    speaker = sc.default_speaker()
    print("[AUDIO] System audio device:")
    print("        ", speaker.name)

    microphone = sc.get_microphone(
        speaker.name,
        include_loopback=True
    )

    encoder = Encoder(
        AUDIO_SAMPLE_RATE,
        AUDIO_CHANNELS,
        "audio"
    )
    encoder.bitrate = OPUS_BITRATE

    try:

        viewer_address = wait_for_hello(server, b"AUDIO_HELLO")
        print(f"[AUDIO] Viewer connected: {viewer_address}")
        sequence = 0
        audio_frames = 0

        with microphone.recorder(
            samplerate=AUDIO_SAMPLE_RATE,
            channels=AUDIO_CHANNELS,
            blocksize=AUDIO_CAPTURE_FRAMES
        ) as recorder:

            while True:

                captured_audio = np.asarray(
                    recorder.record(
                        numframes=AUDIO_CAPTURE_FRAMES
                    ),
                    dtype=np.float32
                )

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

                    pcm = np.clip(
                        audio * 32767,
                        -32768,
                        32767
                    ).astype(np.int16)

                    encoded = encoder.encode(
                        pcm.tobytes(),
                        AUDIO_FRAME_SIZE
                    )

                    server.sendto(
                        encode_audio_packet(sequence, encoded),
                        viewer_address
                    )

                    sequence = (sequence + 1) & 0xFFFFFFFF
                    audio_frames += 1

                    if audio_frames % 50 == 0:
                        print(
                            f"[AUDIO] Sent {audio_frames} frames; "
                            f"level={float(np.max(np.abs(audio))):.5f}"
                        )

    except Exception as error:
        print("[AUDIO] Error:", error)

    finally:
        server.close()