import os


HOST = "0.0.0.0"
SENDER_IP = "127.0.0.1"

VIDEO_PORT = 5000
AUDIO_PORT = 5001
VIDEO_CHUNK_SIZE = 1200
VIDEO_CHUNK_HEADER_FORMAT = "!IHHB"
FULL_REFRESH_SECONDS = 1
KEYFRAME_PACKET_DELAY = 0.001

FPS = 30
VIDEO_BITRATE = 5_000_000
MONITOR = 1

AUDIO_SAMPLE_RATE = 48000
AUDIO_CHANNELS = 2
AUDIO_FRAME_SIZE = 960
AUDIO_CAPTURE_FRAMES = AUDIO_FRAME_SIZE * 4
OPUS_BITRATE = 128000


def configure_opus_library():

    if os.name != "nt":
        return

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