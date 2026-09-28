import io
import socket
import struct
import time
import threading

import mss
import numpy as np
import soundcard as sc
from PIL import Image


# =========================
# CONFIGURAÇÕES
# =========================

HOST = "0.0.0.0"

VIDEO_PORT = 5000
AUDIO_PORT = 5001

FPS = 30
JPEG_QUALITY = 65

MONITOR = 1

AUDIO_SAMPLE_RATE = 48000
AUDIO_CHANNELS = 2
AUDIO_CHUNK_FRAMES = 1024


# =========================
# FUNÇÕES DE REDE
# =========================

def send_packet(sock, data):
    """
    Envia:
        4 bytes -> tamanho do pacote
        N bytes -> dados
    """

    header = struct.pack("!I", len(data))

    sock.sendall(header)
    sock.sendall(data)


# =========================
# VÍDEO
# =========================

def video_server():
    print("[VIDEO] Starting server...")

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    server.setsockopt(
        socket.SOL_SOCKET,
        socket.SO_REUSEADDR,
        1
    )

    server.bind((HOST, VIDEO_PORT))
    server.listen(1)

    print(f"[VIDEO] Waiting for viewer on port {VIDEO_PORT}...")

    with mss.mss() as sct:

        monitor = sct.monitors[MONITOR]

        while True:

            conn, address = server.accept()

            print(f"[VIDEO] Viewer connected: {address}")

            try:

                frame_interval = 1 / FPS

                while True:

                    start_time = time.perf_counter()

                    # Captura da tela
                    screenshot = sct.grab(monitor)

                    # Converte para PIL
                    image = Image.frombytes(
                        "RGB",
                        screenshot.size,
                        screenshot.rgb
                    )

                    # JPEG em memória
                    buffer = io.BytesIO()

                    image.save(
                        buffer,
                        format="JPEG",
                        quality=JPEG_QUALITY
                    )

                    frame = buffer.getvalue()

                    # Envia frame
                    send_packet(conn, frame)

                    # Mantém aproximadamente 30 FPS
                    elapsed = time.perf_counter() - start_time

                    remaining = frame_interval - elapsed

                    if remaining > 0:
                        time.sleep(remaining)

            except (
                ConnectionResetError,
                BrokenPipeError,
                ConnectionAbortedError
            ):

                print("[VIDEO] Viewer disconnected.")

            except Exception as e:

                print("[VIDEO] Error:", e)

            finally:

                conn.close()

                print("[VIDEO] Waiting for viewer...")


# =========================
# ÁUDIO
# =========================

def audio_server():
    print("[AUDIO] Starting server...")

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    server.setsockopt(
        socket.SOL_SOCKET,
        socket.SO_REUSEADDR,
        1
    )

    server.bind((HOST, AUDIO_PORT))
    server.listen(1)

    print(f"[AUDIO] Waiting for viewer on port {AUDIO_PORT}...")

    # Dispositivo de áudio padrão do Windows
    speaker = sc.default_speaker()

    print("[AUDIO] Default speaker:")
    print("       ", speaker.name)

    # Cria um dispositivo de loopback.
    #
    # Isso captura aquilo que o Windows
    # está reproduzindo pelos alto-falantes/fone.
    microphone = sc.get_microphone(
        speaker.name,
        include_loopback=True
    )

    while True:

        conn, address = server.accept()

        print(f"[AUDIO] Viewer connected: {address}")

        try:

            with microphone.recorder(
                samplerate=AUDIO_SAMPLE_RATE,
                channels=AUDIO_CHANNELS
            ) as recorder:

                while True:

                    # Captura aproximadamente 21ms
                    audio = recorder.record(
                        numframes=AUDIO_CHUNK_FRAMES
                    )

                    # Garante float32
                    audio = np.asarray(
                        audio,
                        dtype=np.float32
                    )

                    # Converte para bytes
                    audio_bytes = audio.tobytes()

                    # Envia
                    send_packet(
                        conn,
                        audio_bytes
                    )

        except (
            ConnectionResetError,
            BrokenPipeError,
            ConnectionAbortedError
        ):

            print("[AUDIO] Viewer disconnected.")

        except Exception as e:

            print("[AUDIO] Error:", e)

        finally:

            conn.close()

            print("[AUDIO] Waiting for viewer...")


# =========================
# MAIN
# =========================

def main():

    print("=" * 50)
    print("        SCREEN + AUDIO SERVER")
    print("=" * 50)

    print()
    print(f"Video port: {VIDEO_PORT}")
    print(f"Audio port: {AUDIO_PORT}")
    print(f"Video: {FPS} FPS")
    print(
        f"Audio: {AUDIO_SAMPLE_RATE} Hz / "
        f"{AUDIO_CHANNELS} channels"
    )
    print()

    # Vídeo em uma thread
    video_thread = threading.Thread(
        target=video_server,
        daemon=True
    )

    # Áudio em outra thread
    audio_thread = threading.Thread(
        target=audio_server,
        daemon=True
    )

    video_thread.start()
    audio_thread.start()

    # Mantém o programa vivo
    video_thread.join()
    audio_thread.join()


if __name__ == "__main__":
    main()