import socket
import threading

import av
import tkinter as tk

from PIL import Image, ImageTk

from media_protocol import parse_video_packet
from screen_config import SENDER_IP, VIDEO_PORT


class VideoReceiver:

    def __init__(self, root):
        self.root = root
        self.socket = None
        self.running = True
        self.latest_image = None
        self.lock = threading.Lock()
        self.decoder = av.CodecContext.create("h264", "r")
        self.needs_keyframe = False
        self.label = tk.Label(root, bg="black")
        self.label.pack(expand=True, fill="both")

    def connect(self):
        print(f"[VIDEO] Connecting to {SENDER_IP}:{VIDEO_PORT}...")
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_RCVBUF,
            4 * 1024 * 1024
        )
        self.socket.sendto(b"VIDEO_HELLO", (SENDER_IP, VIDEO_PORT))
        print("[VIDEO] Hello sent.")

    def receive_loop(self):
        current_frame_id = None
        chunks = {}
        expected_chunks = None
        current_keyframe = False
        previous_frame_complete = True

        try:
            while self.running:
                parsed = parse_video_packet(
                    self.socket.recvfrom(65535)[0]
                )
                if parsed is None:
                    continue

                frame_id, chunk_id, chunk_count, is_keyframe, payload = parsed

                if current_frame_id is None or frame_id > current_frame_id:
                    if current_frame_id is not None and (
                        frame_id > current_frame_id + 1
                        or not previous_frame_complete
                    ):
                        self.needs_keyframe = True
                    current_frame_id = frame_id
                    chunks = {}
                    expected_chunks = chunk_count
                    current_keyframe = is_keyframe
                    previous_frame_complete = False

                if frame_id != current_frame_id:
                    continue
                if chunk_count != expected_chunks:
                    continue
                if is_keyframe != current_keyframe:
                    continue

                chunks[chunk_id] = payload
                if len(chunks) != expected_chunks:
                    continue

                encoded_frame = b"".join(
                    chunks[index]
                    for index in range(expected_chunks)
                )
                chunks = {}
                previous_frame_complete = True

                if self.needs_keyframe and not current_keyframe:
                    continue
                if current_keyframe:
                    self.decoder = av.CodecContext.create("h264", "r")

                try:
                    decoded_frames = self.decoder.decode(
                        av.Packet(encoded_frame)
                    )
                    for decoded_frame in decoded_frames:
                        image = Image.fromarray(
                            decoded_frame.to_ndarray(format="rgb24")
                        )
                        with self.lock:
                            self.latest_image = image
                    if decoded_frames and current_keyframe:
                        self.needs_keyframe = False
                except av.error.InvalidDataError:
                    self.decoder = av.CodecContext.create("h264", "r")
                    self.needs_keyframe = True

        except Exception as error:
            if self.running:
                print("[VIDEO] Receive error:", error)

    def update_screen(self):
        with self.lock:
            image = self.latest_image.copy() if self.latest_image else None

        if image:
            width = self.root.winfo_width()
            height = self.root.winfo_height()
            if width > 1 and height > 1:
                image.thumbnail(
                    (width, height),
                    Image.Resampling.LANCZOS
                )
            photo = ImageTk.PhotoImage(image)
            self.label.configure(image=photo)
            self.label.image = photo

        self.root.after(16, self.update_screen)

    def start(self):
        self.connect()
        threading.Thread(
            target=self.receive_loop,
            daemon=True
        ).start()
        self.update_screen()

    def close(self):
        self.running = False
        if self.socket:
            self.socket.close()