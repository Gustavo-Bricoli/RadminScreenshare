import io
import socket
import struct
import time
import mss
from PIL import Image


# =========================
# CONFIGURATION
# =========================

HOST = "0.0.0.0"
PORT = 5000

FPS = 30
JPEG_QUALITY = 65

# 1 = primary monitor
MONITOR = 1


def send_all(sock, data):
    """Send all bytes through the socket."""
    sock.sendall(data)


def main():

    with mss.mss() as sct:

        monitor = sct.monitors[MONITOR]

        print("Waiting for viewer...")
        print(f"Port: {PORT}")

        # Create TCP server
        server = socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM
        )

        server.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_REUSEADDR,
            1
        )

        server.bind((HOST, PORT))
        server.listen(1)

        while True:

            conn, address = server.accept()

            print(f"Viewer connected: {address}")

            try:

                frame_interval = 1 / FPS

                while True:

                    start_time = time.perf_counter()

                    # Capture screen
                    screenshot = sct.grab(monitor)

                    # Convert MSS image to PIL
                    image = Image.frombytes(
                        "RGB",
                        screenshot.size,
                        screenshot.rgb
                    )

                    # Encode JPEG in memory
                    buffer = io.BytesIO()

                    image.save(
                        buffer,
                        format="JPEG",
                        quality=JPEG_QUALITY
                    )

                    frame = buffer.getvalue()

                    # Send frame size first
                    header = struct.pack(
                        "!I",
                        len(frame)
                    )

                    send_all(conn, header)

                    # Send JPEG
                    send_all(conn, frame)

                    # Maintain approximately 30 FPS
                    elapsed = (
                        time.perf_counter()
                        - start_time
                    )

                    remaining = (
                        frame_interval - elapsed
                    )

                    if remaining > 0:
                        time.sleep(remaining)

            except (
                ConnectionResetError,
                BrokenPipeError,
                ConnectionAbortedError
            ):

                print("Viewer disconnected.")

            except Exception as e:

                print("Connection error:", e)

            finally:

                conn.close()

                print("Waiting for viewer...")


if __name__ == "__main__":
    main()