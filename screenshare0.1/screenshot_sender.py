import io
import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from PIL import ImageGrab


# =========================
# CONFIGURATION
# =========================

PORT = 5000
INTERVAL = 1/30  # seconds


# This contains the most recent screenshot.
latest_screenshot = None

lock = threading.Lock()


def take_screenshot():
    global latest_screenshot

    while True:
        try:
            screenshot = ImageGrab.grab()

            # Convert screenshot to JPEG in memory
            buffer = io.BytesIO()

            screenshot.convert("RGB").save(
                buffer,
                format="JPEG",
                quality=80
            )

            with lock:
                latest_screenshot = buffer.getvalue()

            print(
                f"Screenshot updated at "
                f"{time.strftime('%H:%M:%S')}"
            )

        except Exception as e:
            print("Screenshot error:", e)

        time.sleep(INTERVAL)


class ScreenshotHandler(BaseHTTPRequestHandler):

    def do_GET(self):

        if self.path != "/screenshot":
            self.send_response(404)
            self.end_headers()
            return

        with lock:
            screenshot = latest_screenshot

        if screenshot is None:
            self.send_response(503)
            self.end_headers()
            self.wfile.write(b"Screenshot not ready")
            return

        self.send_response(200)

        self.send_header(
            "Content-Type",
            "image/jpeg"
        )

        self.send_header(
            "Content-Length",
            str(len(screenshot))
        )

        self.end_headers()

        self.wfile.write(screenshot)

    def log_message(self, format, *args):
        # Prevent HTTP requests from cluttering the console
        pass


def start_server():
    server = HTTPServer(
        ("0.0.0.0", PORT),
        ScreenshotHandler
    )

    print(f"Server running on port {PORT}")
    print(
        f"Your friend should access: "
        f"http://YOUR_RADMIN_IP:{PORT}/screenshot"
    )

    server.serve_forever()


# Start screenshot thread
screenshot_thread = threading.Thread(
    target=take_screenshot,
    daemon=True
)

screenshot_thread.start()


# Start HTTP server
start_server()