import threading
import time

from audio_sender import run_audio_server
from screen_config import AUDIO_PORT, FPS, OPUS_BITRATE, VIDEO_PORT
from video_sender import run_video_server


def main():

    print("=" * 55)
    print("          SCREEN + AUDIO SERVER")
    print("=" * 55)
    print()
    print(f"Video: UDP {VIDEO_PORT}")
    print(f"Audio: UDP {AUDIO_PORT}")
    print(f"Video: {FPS} FPS")
    print(f"Audio: Opus {OPUS_BITRATE // 1000} kbps")
    print()

    threading.Thread(
        target=run_video_server,
        daemon=True
    ).start()

    threading.Thread(
        target=run_audio_server,
        daemon=True
    ).start()

    try:

        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print()
        print("Stopping server...")