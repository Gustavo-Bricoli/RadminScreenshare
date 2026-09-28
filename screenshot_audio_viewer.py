import io
import socket
import struct
import threading
import queue

import tkinter as tk

import numpy as np
import sounddevice as sd

from PIL import Image, ImageTk


# =========================
# CONFIGURAÇÕES
# =========================

SENDER_IP = "26.123.65.96"

VIDEO_PORT = 5000
AUDIO_PORT = 5001

AUDIO_SAMPLE_RATE = 48000
AUDIO_CHANNELS = 2

AUDIO_CHUNK_FRAMES = 1024


# =========================
# RECEBER PACOTE
# =========================

def receive_packet(sock):
    """
    Recebe:

        4 bytes -> tamanho
        N bytes -> dados
    """

    header = receive_exactly(sock, 4)

    size = struct.unpack(
        "!I",
        header
    )[0]

    return receive_exactly(
        sock,
        size
    )


def receive_exactly(sock, size):

    data = bytearray()

    while len(data) < size:

        chunk = sock.recv(
            size - len(data)
        )

        if not chunk:
            raise ConnectionError(
                "Connection closed."
            )

        data.extend(chunk)

    return bytes(data)


# =========================
# ÁUDIO
# =========================

class AudioReceiver:

    def __init__(self):

        self.socket = None

        # Buffer de áudio.
        #
        # Mantemos limitado para evitar que
        # o áudio acumule vários segundos
        # de atraso.
        self.audio_queue = queue.Queue(
            maxsize=50
        )

        self.running = True

    def connect(self):

        print(
            f"[AUDIO] Connecting to "
            f"{SENDER_IP}:{AUDIO_PORT}..."
        )

        self.socket = socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM
        )

        self.socket.connect(
            (
                SENDER_IP,
                AUDIO_PORT
            )
        )

        print("[AUDIO] Connected!")

    def receive_loop(self):

        try:

            while self.running:

                audio_bytes = receive_packet(
                    self.socket
                )

                # Converte bytes -> float32
                audio = np.frombuffer(
                    audio_bytes,
                    dtype=np.float32
                )

                # Converte para estéreo
                audio = audio.reshape(
                    (-1, AUDIO_CHANNELS)
                )

                # Coloca no buffer
                try:

                    self.audio_queue.put_nowait(
                        audio.copy()
                    )

                except queue.Full:

                    # Se estiver atrasado,
                    # joga fora o pacote mais antigo.
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

            print(
                "[AUDIO] Connection error:",
                e
            )

            self.running = False

    def audio_callback(
        self,
        outdata,
        frames,
        time,
        status
    ):

        if status:
            print(
                "[AUDIO]",
                status
            )

        try:

            audio = self.audio_queue.get_nowait()

            if len(audio) >= frames:

                outdata[:] = audio[:frames]

            else:

                outdata[:len(audio)] = audio

                outdata[len(audio):] = 0

        except queue.Empty:

            # Sem áudio disponível
            outdata[:] = 0

    def start(self):

        self.connect()

        # Recepção acontece em outra thread
        thread = threading.Thread(
            target=self.receive_loop,
            daemon=True
        )

        thread.start()

        # Saída de áudio
        self.stream = sd.OutputStream(
            samplerate=AUDIO_SAMPLE_RATE,
            channels=AUDIO_CHANNELS,
            dtype="float32",
            blocksize=AUDIO_CHUNK_FRAMES,
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


# =========================
# VÍDEO
# =========================

class VideoReceiver:

    def __init__(self, root):

        self.root = root

        self.socket = None

        self.latest_image = None

        self.running = True

        # Interface
        self.label = tk.Label(
            root,
            bg="black"
        )

        self.label.pack(
            expand=True,
            fill="both"
        )

    def connect(self):

        print(
            f"[VIDEO] Connecting to "
            f"{SENDER_IP}:{VIDEO_PORT}..."
        )

        self.socket = socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM
        )

        self.socket.connect(
            (
                SENDER_IP,
                VIDEO_PORT
            )
        )

        print("[VIDEO] Connected!")

    def receive_loop(self):

        try:

            while self.running:

                frame = receive_packet(
                    self.socket
                )

                image = Image.open(
                    io.BytesIO(frame)
                )

                image.load()

                # Só precisamos guardar o frame
                # mais recente.
                self.latest_image = image.copy()

        except Exception as e:

            print(
                "[VIDEO] Connection error:",
                e
            )

            self.running = False

    def update_screen(self):

        if self.latest_image:

            image = self.latest_image

            # Redimensiona para caber na janela
            width = self.root.winfo_width()
            height = self.root.winfo_height()

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

        # Atualiza aproximadamente
        # 60 vezes por segundo
        self.root.after(
            16,
            self.update_screen
        )

    def start(self):

        self.connect()

        thread = threading.Thread(
            target=self.receive_loop,
            daemon=True
        )

        thread.start()

        self.update_screen()

    def close(self):

        self.running = False

        if self.socket:
            self.socket.close()


# =========================
# MAIN
# =========================

def main():

    print("=" * 50)
    print("       SCREEN + AUDIO VIEWER")
    print("=" * 50)

    root = tk.Tk()

    root.title(
        "Screen Share + Audio"
    )

    root.geometry(
        "1280x720"
    )

    video = VideoReceiver(root)

    audio = AudioReceiver()

    # Inicia vídeo
    video.start()

    # Inicia áudio
    audio.start()

    def close():

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