"""Small self-closing warning shown before a mandatory break."""

import ctypes
import sys
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def _work_area():
    try:
        from ctypes import wintypes

        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", wintypes.LONG),
                ("top", wintypes.LONG),
                ("right", wintypes.LONG),
                ("bottom", wintypes.LONG),
            ]

        rect = RECT()
        if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
            return rect.left, rect.top, rect.right, rect.bottom
    except Exception:
        pass
    return 0, 0, 1280, 720


def show_break_notification(minutes: int, duration_ms: int = 8000):
    minutes = max(1, int(minutes))
    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.configure(bg="#f6c344")

    width, height = 390, 118
    left, top, right, bottom = _work_area()
    x = max(left, right - width - 18)
    y = max(top, bottom - height - 18)
    root.geometry(f"{width}x{height}+{x}+{y}")

    frame = tk.Frame(root, bg="#1a1a2e", highlightbackground="#f6c344", highlightthickness=3)
    frame.pack(fill=tk.BOTH, expand=True)
    tk.Label(
        frame,
        text="Скоро перерыв",
        font=("Arial", 16, "bold"),
        fg="#f6c344",
        bg="#1a1a2e",
    ).pack(pady=(16, 5))
    suffix = "минуту" if minutes == 1 else "минут"
    tk.Label(
        frame,
        text=f"Обязательный перерыв начнётся через {minutes} {suffix}",
        font=("Arial", 11),
        fg="#ffffff",
        bg="#1a1a2e",
    ).pack()

    root.bind("<Button-1>", lambda _event: root.destroy())
    root.after(max(1000, int(duration_ms)), root.destroy)
    root.mainloop()


if __name__ == "__main__":
    try:
        value = int(sys.argv[1])
    except (IndexError, TypeError, ValueError):
        value = 1
    show_break_notification(value)
