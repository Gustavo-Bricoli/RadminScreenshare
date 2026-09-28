import socket
import time
from fractions import Fraction

import av
import mss
import numpy as np
from av.video.frame import PictureType

from media_protocol import send_video_frame, wait_for_hello
from screen_config import (
    FPS,
    FULL_REFRESH_SECONDS,
    HOST,
    MONITOR,
    VIDEO_BITRATE,
    VIDEO_PORT
)


def create_encoder(width, height):

    encoder = av.CodecContext.create("libx264", "w")
    encoder.width = width
    encoder.height = height
    encoder.pix_fmt = "yuv420p"
    encoder.time_base = Fraction(1, FPS)
    encoder.framerate = Fraction(FPS, 1)
    encoder.bit_rate = VIDEO_BITRATE
    encoder.options = {
        "preset": "ultrafast",
        "tune": "zerolatency",
        "g": str(FPS * FULL_REFRESH_SECONDS),
        "keyint_min": str(FPS * FULL_REFRESH_SECONDS),
        "forced-idr": "1",
        "repeat-headers": "1",
        "sc_threshold": "0",
        "bframes": "0",
        "rc-lookahead": "0",
        "threads": "1"
    }
    encoder.open()
    return encoder


def run_video_server():

    print("[VIDEO] Starting server...")
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind((HOST, VIDEO_PORT))

    print(
        f"[VIDEO] Waiting for viewer on UDP port {VIDEO_PORT}..."
    )
    viewer_address = wait_for_hello(server, b"VIDEO_HELLO")
    print(f"[VIDEO] Viewer connected: {viewer_address}")

    try:

        with mss.MSS() as capture:

            monitor = capture.monitors[MONITOR]
            encoder = None
            frame_id = 0
            frame_interval = 1 / FPS

            while True:

                start = time.perf_counter()
                screenshot = capture.grab(monitor)
                width, height = screenshot.size

                if encoder is None:
                    encoder = create_encoder(width, height)

                image = np.frombuffer(
                    screenshot.rgb,
                    dtype=np.uint8
                ).reshape((height, width, 3))

                video_frame = av.VideoFrame.from_ndarray(
                    image,
                    format="rgb24"
                )
                video_frame.pts = frame_id

                if frame_id % (FPS * FULL_REFRESH_SECONDS) == 0:
                    video_frame.pict_type = PictureType.I

                for encoded_packet in encoder.encode(video_frame):

                    encoded_bytes = bytes(encoded_packet)
                    chunk_count = send_video_frame(
                        server,
                        viewer_address,
                        frame_id,
                        encoded_bytes,
                        encoded_packet.is_keyframe
                    )

                    if encoded_packet.is_keyframe or frame_id % FPS == 0:
                        print(
                            f"[VIDEO] Sent frame={frame_id}; "
                            f"bytes={len(encoded_bytes)}; "
                            f"chunks={chunk_count}; "
                            f"keyframe={encoded_packet.is_keyframe}"
                        )

                frame_id = (frame_id + 1) & 0xFFFFFFFF
                remaining = frame_interval - (
                    time.perf_counter() - start
                )

                if remaining > 0:
                    time.sleep(remaining)

    except Exception as error:
        print("[VIDEO] Error:", error)

    finally:
        server.close()