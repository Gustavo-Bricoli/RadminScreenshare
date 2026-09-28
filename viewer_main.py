import os
import sys
import traceback

import tkinter as tk

from audio_viewer import AudioReceiver
from video_viewer import VideoReceiver


CRASH_LOG = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "viewer_crash.log"
)


def log_exception(label, exception_type, exception, traceback_object):
    with open(CRASH_LOG, "a", encoding="utf-8") as log_file:
        log_file.write(f"\n[{label}]\n")
        traceback.print_exception(
            exception_type,
            exception,
            traceback_object,
            file=log_file
        )


def handle_exception(exception_type, exception, traceback_object):
    if exception_type is not KeyboardInterrupt:
        log_exception(
            "UNHANDLED GUI EXCEPTION",
            exception_type,
            exception,
            traceback_object
        )
    sys.__excepthook__(exception_type, exception, traceback_object)


sys.excepthook = handle_exception


def main():
    print("=" * 55)
    print("          SCREEN + AUDIO VIEWER")
    print("=" * 55)
    print()

    root = tk.Tk()
    root.title("Screen Share + Audio")
    root.geometry("1280x720")

    video = VideoReceiver(root)
    audio = AudioReceiver()

    try:
        video.start()
        audio.start()
    except Exception as error:
        print("Failed to connect:", error)
        root.destroy()
        return

    def close():
        print("Closing viewer...")
        video.close()
        audio.close()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", close)
    root.mainloop()