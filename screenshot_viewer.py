import io
import tkinter as tk
from tkinter import messagebox

import requests
from PIL import Image, ImageTk


# =========================
# CONFIGURATION
# =========================

YOUR_RADMIN_IP = "26.160.75.111"
PORT = 5000

INTERVAL = 1 / 30  # seconds


class ScreenshotViewer:

    def __init__(self, root):

        self.root = root

        self.root.title("Screen Share")
        self.root.geometry("1000x700")

        self.image_label = tk.Label(
            root,
            text="Waiting for screenshot..."
        )

        self.image_label.pack(
            expand=True,
            fill="both"
        )

        self.status_label = tk.Label(
            root,
            text="Connecting..."
        )

        self.status_label.pack(
            pady=5
        )

        self.update_screenshot()

    def update_screenshot(self):

        url = (
            f"http://{YOUR_RADMIN_IP}:"
            f"{PORT}/screenshot"
        )

        try:

            response = requests.get(
                url,
                timeout=10
            )

            response.raise_for_status()

            image = Image.open(
                io.BytesIO(response.content)
            )

            # Resize while maintaining aspect ratio
            image.thumbnail(
                (950, 620),
                Image.Resampling.LANCZOS
            )

            photo = ImageTk.PhotoImage(image)

            self.image_label.configure(
                image=photo,
                text=""
            )

            # Keep reference so Tkinter doesn't delete it
            self.image_label.image = photo

            self.status_label.configure(
                text="Connected — screenshot updated"
            )

        except Exception as e:

            self.status_label.configure(
                text=f"Connection error: {e}"
            )

        # Try again after 60 seconds
        self.root.after(
            int(INTERVAL * 1000),
            self.update_screenshot
        )

root = tk.Tk()

app = ScreenshotViewer(root)

root.mainloop()