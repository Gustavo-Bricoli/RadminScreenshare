import queue
import socket
import threading

import numpy as np
import sounddevice as sd

from media_protocol import parse_audio_packet
from screen_config import (
    AUDIO_CHANNELS,
    AUDIO_FRAME_SIZE,
    AUDIO_PORT,
    AUDIO_SAMPLE_RATE,
    SENDER_IP,
    configure_opus_library
)


class AudioReceiver:

    def __init__(self):
        configure_opus_library()
        from opuslib import Decoder
        self.socket = None
        self.running = True
        self.audio_queue = queue.Queue(maxsize=20)
        self.pending_audio = np.empty((0, AUDIO_CHANNELS), dtype=np.float32)
        self.decoder = Decoder(AUDIO_SAMPLE_RATE, AUDIO_CHANNELS)
        self.last_sequence = None
        self.audio_connected = False
        self.stream = None
        self.audio_received = 0
        self.audio_lost = 0

    def _queue_audio(self, audio):
        try:
            self.audio_queue.put_nowait(audio.copy())
        except queue.Full:
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self.audio_queue.put_nowait(audio.copy())
            except queue.Full:
                pass

    def connect(self):
        print(f"[AUDIO] Connecting to {SENDER_IP}:{AUDIO_PORT}...")
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_RCVBUF,
            1024 * 1024
        )
        self.socket.settimeout(1.0)
        self.socket.sendto(b"AUDIO_HELLO", (SENDER_IP, AUDIO_PORT))
        print("[AUDIO] Hello sent.")

    def receive_loop(self):
        try:
            while self.running:
                try:
                    packet, _ = self.socket.recvfrom(4096)
                except socket.timeout:
                    if not self.audio_connected:
                        self.socket.sendto(
                            b"AUDIO_HELLO",
                            (SENDER_IP, AUDIO_PORT)
                        )
                    continue
                except ConnectionResetError:
                    self.audio_connected = False
                    continue

                parsed = parse_audio_packet(packet)
                if parsed is None:
                    continue

                sequence, encoded = parsed
                self.audio_connected = True
                self.audio_received += 1

                if self.last_sequence is not None:
                    expected = (self.last_sequence + 1) & 0xFFFFFFFF
                    missing = (sequence - expected) & 0xFFFFFFFF

                    if missing > 0x80000000:
                        continue

                    self.audio_lost += missing

                    for _ in range(min(missing, 5)):
                        try:
                            concealed = self.decoder.decode(
                                b"",
                                AUDIO_FRAME_SIZE
                            )
                            self._queue_audio(
                                np.frombuffer(
                                    concealed,
                                    dtype=np.int16
                                ).astype(np.float32).reshape(
                                    (-1, AUDIO_CHANNELS)
                                ) / 32768.0
                            )
                        except Exception:
                            break

                self.last_sequence = sequence

                try:
                    pcm_bytes = self.decoder.decode(encoded, AUDIO_FRAME_SIZE)
                except Exception as error:
                    print("[AUDIO] Dropping invalid packet:", error)
                    continue

                audio = np.frombuffer(
                    pcm_bytes,
                    dtype=np.int16
                ).astype(np.float32).reshape(
                    (-1, AUDIO_CHANNELS)
                ) / 32768.0
                self._queue_audio(audio)

                if self.audio_received % 250 == 0:
                    print(
                        f"[AUDIO] Received={self.audio_received}; "
                        f"lost={self.audio_lost}"
                    )

        except Exception as error:
            if self.running:
                print("[AUDIO] Receive error:", error)

    def audio_callback(self, outdata, frames, time_info, status):
        if status:
            print("[AUDIO]", status)

        audio = self.pending_audio
        while len(audio) < frames:
            try:
                audio = np.concatenate(
                    (audio, self.audio_queue.get_nowait()),
                    axis=0
                )
            except queue.Empty:
                break

        outdata[:] = 0
        sample_count = min(len(audio), frames)
        if sample_count:
            outdata[:sample_count] = audio[:sample_count]
        self.pending_audio = audio[sample_count:].copy()

    def start(self):
        self.connect()
        threading.Thread(
            target=self.receive_loop,
            daemon=True
        ).start()
        self.stream = sd.OutputStream(
            samplerate=AUDIO_SAMPLE_RATE,
            channels=AUDIO_CHANNELS,
            dtype="float32",
            blocksize=AUDIO_FRAME_SIZE,
            callback=self.audio_callback
        )
        self.stream.start()
        print("[AUDIO] Playback started.")

    def close(self):
        self.running = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
        if self.socket:
            self.socket.close()