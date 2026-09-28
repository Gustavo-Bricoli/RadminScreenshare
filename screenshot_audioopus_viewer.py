import os
import socket
import struct
import threading
import queue
from fractions import Fraction

import av
import tkinter as tk

import numpy as np
import sounddevice as sd

from PIL import Image, ImageTk


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

from opuslib import Decoder


# ============================================================
# CONFIGURATION
# ============================================================

SENDER_IP = "26.123.65.96"

VIDEO_PORT = 5000
AUDIO_PORT = 5001
VIDEO_CHUNK_HEADER_SIZE = 8

AUDIO_SAMPLE_RATE = 48000
AUDIO_CHANNELS = 2

AUDIO_FRAME_SIZE = 960


# ============================================================
# VIDEO UDP PACKETS
# ============================================================

# AUDIO RECEIVER
# ============================================================

class AudioReceiver:

    def __init__(self):

        self.socket = None

        self.running = True

        self.audio_queue = queue.Queue(
            maxsize=20
        )

        self.pending_audio = np.empty(
            (0, AUDIO_CHANNELS),
            dtype=np.float32
        )

        self.decoder = Decoder(
            AUDIO_SAMPLE_RATE,
            AUDIO_CHANNELS
        )

        self.last_sequence = None

        self.stream = None

    # --------------------------------------------------------

    def connect(self):

        print(
            f"[AUDIO] Connecting to "
            f"{SENDER_IP}:{AUDIO_PORT}..."
        )

        self.socket = socket.socket(
            socket.AF_INET,
            socket.SOCK_DGRAM
        )

        # Tell sender where we are
        self.socket.sendto(
            b"AUDIO_HELLO",
            (
                SENDER_IP,
                AUDIO_PORT
            )
        )

        print(
            "[AUDIO] Hello sent."
        )

    # --------------------------------------------------------

    def receive_loop(self):

        try:

            while self.running:

                packet, address = (
                    self.socket.recvfrom(4096)
                )

                if len(packet) < 4:
                    continue

                # Read sequence number
                sequence = struct.unpack(
                    "!I",
                    packet[:4]
                )[0]

                encoded = packet[4:]

                # Detect old/out-of-order packets
                if self.last_sequence is not None:

                    expected = (
                        self.last_sequence + 1
                    ) & 0xFFFFFFFF

                    if sequence != expected:

                        # Packet was lost or arrived
                        # out of order.
                        pass

                self.last_sequence = sequence

                try:

                    # Decode Opus
                    pcm_bytes = self.decoder.decode(
                        encoded,
                        AUDIO_FRAME_SIZE
                    )

                except Exception as decode_error:

                    print(
                        "[AUDIO] Dropping invalid packet:",
                        decode_error
                    )

                    continue

                # Convert int16 -> float32
                audio = np.frombuffer(
                    pcm_bytes,
                    dtype=np.int16
                ).astype(
                    np.float32
                ) / 32768.0

                audio = audio.reshape(
                    (-1, AUDIO_CHANNELS)
                )

                # Add to playback queue
                try:

                    self.audio_queue.put_nowait(
                        audio.copy()
                    )

                except queue.Full:

                    # Drop old audio instead of
                    # accumulating latency.
                    try:

                        self.audio_queue.get_nowait()

                    except queue.Empty:
                        pass

                    try:

                        self.audio_queue.put_nowait(
                            audio.copy()
                        )

                    except queue.Full:
                        pass

        except Exception as e:

            if self.running:

                print(
                    "[AUDIO] Receive error:",
                    e
                )

    # --------------------------------------------------------

    def audio_callback(
        self,
        outdata,
        frames,
        time_info,
        status
    ):

        if status:
            print(
                "[AUDIO]",
                status
            )

        audio = self.pending_audio

        while len(audio) < frames:

            try:

                next_audio = self.audio_queue.get_nowait()
                audio = np.concatenate(
                    (audio, next_audio),
                    axis=0
                )

            except queue.Empty:

                break

        outdata[:] = 0

        sample_count = min(
            len(audio),
            frames
        )

        if sample_count:

            outdata[:sample_count] = (
                audio[:sample_count]
            )

        self.pending_audio = audio[sample_count:].copy()

    # --------------------------------------------------------

    def start(self):

        self.connect()

        thread = threading.Thread(
            target=self.receive_loop,
            daemon=True
        )

        thread.start()

        self.stream = sd.OutputStream(
            samplerate=AUDIO_SAMPLE_RATE,
            channels=AUDIO_CHANNELS,
            dtype="float32",
            blocksize=AUDIO_FRAME_SIZE,
            callback=self.audio_callback
        )

        self.stream.start()

        print(
            "[AUDIO] Playback started."
        )

    # --------------------------------------------------------

    def close(self):

        self.running = False

        if self.stream:

            self.stream.stop()
            self.stream.close()

        if self.socket:

            self.socket.close()


# ============================================================
# VIDEO RECEIVER
# ============================================================

class VideoReceiver:

    def __init__(self, root):

        self.root = root

        self.socket = None

        self.running = True

        self.latest_image = None

        self.lock = threading.Lock()

        self.decoder = av.CodecContext.create(
            "h264",
            "r"
        )

        self.label = tk.Label(
            root,
            bg="black"
        )

        self.label.pack(
            expand=True,
            fill="both"
        )

    # --------------------------------------------------------

    def connect(self):

        print(
            f"[VIDEO] Connecting to "
            f"{SENDER_IP}:{VIDEO_PORT}..."
        )

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        self.socket.sendto(
            b"VIDEO_HELLO",
            (SENDER_IP, VIDEO_PORT)
        )

        print(
            "[VIDEO] Hello sent."
        )

    # --------------------------------------------------------

    def receive_loop(self):

        try:

            current_frame_id = None
            chunks = {}
            expected_chunks = None

            while self.running:

                packet, address = self.socket.recvfrom(65535)

                if len(packet) <= VIDEO_CHUNK_HEADER_SIZE:
                    continue

                frame_id, chunk_id, chunk_count = struct.unpack(
                    "!IHH",
                    packet[:VIDEO_CHUNK_HEADER_SIZE]
                )

                if current_frame_id is None or frame_id > current_frame_id:

                    current_frame_id = frame_id
                    chunks = {}
                    expected_chunks = chunk_count

                if frame_id != current_frame_id:
                    continue

                if chunk_count != expected_chunks:
                    continue

                chunks[chunk_id] = packet[VIDEO_CHUNK_HEADER_SIZE:]

                if len(chunks) != expected_chunks:
                    continue

                encoded_frame = b"".join(
                    chunks[index]
                    for index in range(expected_chunks)
                )

                chunks = {}

                try:

                    decoded_frames = self.decoder.decode(
                        av.Packet(encoded_frame)
                    )

                    for decoded_frame in decoded_frames:

                        image = Image.fromarray(
                            decoded_frame.to_ndarray(
                                format="rgb24"
                            )
                        )

                        with self.lock:

                            self.latest_image = image

                except av.error.InvalidDataError:

                    # A lost UDP packet can corrupt one H.264 frame.
                    # Reset the decoder so the next keyframe can recover.
                    self.decoder = av.CodecContext.create(
                        "h264",
                        "r"
                    )

                    continue

        except Exception as e:

            if self.running:

                print(
                    "[VIDEO] Receive error:",
                    e
                )

    # --------------------------------------------------------

    def update_screen(self):

        with self.lock:

            image = self.latest_image

            if image:

                image = image.copy()

        if image:

            width = (
                self.root.winfo_width()
            )

            height = (
                self.root.winfo_height()
            )

            if width > 1 and height > 1:

                image.thumbnail(
                    (width, height),
                    Image.Resampling.LANCZOS
                )

            photo = ImageTk.PhotoImage(
                image
            )

            self.label.configure(
                image=photo
            )

            self.label.image = photo

        self.root.after(
            16,
            self.update_screen
        )

    # --------------------------------------------------------

    def start(self):

        self.connect()

        thread = threading.Thread(
            target=self.receive_loop,
            daemon=True
        )

        thread.start()

        self.update_screen()

    # --------------------------------------------------------

    def close(self):

        self.running = False

        if self.socket:

            self.socket.close()


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 55)

    print(
        "          SCREEN + AUDIO VIEWER"
    )

    print("=" * 55)

    print()

    root = tk.Tk()

    root.title(
        "Screen Share + Audio"
    )

    root.geometry(
        "1280x720"
    )

    video = VideoReceiver(
        root
    )

    audio = AudioReceiver()

    try:

        video.start()

        audio.start()

    except Exception as e:

        print(
            "Failed to connect:",
            e
        )

        root.destroy()

        return

    def close():

        print(
            "Closing viewer..."
        )

        video.close()
        audio.close()

        root.destroy()

    root.protocol(
        "WM_DELETE_WINDOW",
        close
    )

    root.mainloop()


if __name__ == "__main__":
    main()