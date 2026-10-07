import io
import socket
import struct
import tkinter as tk

from PIL import Image, ImageTk


# =========================
# CONFIGURATION
# =========================

YOUR_RADMIN_IP = "26.160.75.111"
PORT = 5000


class Viewer:

    def __init__(self, root):

        self.root = root

        self.root.title(
            "Screen Share - 1080p 30 FPS"
        )

        self.root.geometry(
            "1280x720"
        )

        self.label = tk.Label(
            root,
            bg="black"
        )

        self.label.pack(
            expand=True,
            fill="both"
        )

        self.socket = None

        self.connect()


    def connect(self):

        print(
            f"Connecting to "
            f"{YOUR_RADMIN_IP}:{PORT}..."
        )

        try:
            self.socket = socket.socket(
                socket.AF_INET,
                socket.SOCK_STREAM
            )

            self.socket.connect(
                (
                    YOUR_RADMIN_IP,
                    PORT
                )
            )

        except OSError as exc:
            print(f"Connection failed: {exc}")
            self.root.after(2000, self.connect)
            return

        print("Connected!")

        self.receive_frames()


    def receive_exactly(self, size):

        data = b""

        while len(data) < size:

            chunk = self.socket.recv(
                size - len(data)
            )

            if not chunk:
                raise ConnectionError(
                    "Connection closed."
                )

            data += chunk

        return data


    def receive_frames(self):

        while True:

            # First receive the frame size
            header = self.receive_exactly(4)

            frame_size = struct.unpack(
                "!I",
                header
            )[0]

            # Receive JPEG
            frame = self.receive_exactly(
                frame_size
            )

            # Decode JPEG
            image = Image.open(
                io.BytesIO(frame)
            )

            # Display at original resolution if possible
            photo = ImageTk.PhotoImage(
                image
            )

            self.label.configure(
                image=photo
            )

            self.label.image = photo

            # Allow Tkinter to update
            self.root.update_idletasks()
            self.root.update()


    def close(self):

        if self.socket:
            self.socket.close()

        self.root.destroy()


root = tk.Tk()

viewer = Viewer(root)

root.protocol(
    "WM_DELETE_WINDOW",
    viewer.close
)

root.mainloop()