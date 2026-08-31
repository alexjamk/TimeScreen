"""
TimeScreen Control - Lock Screen
Full-screen blocking window with password authentication.
"""

import ctypes
import json
import os
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.manager import ConfigManager
from config.paths import SERVICE_PIPE_NAME
from service.breaks import get_active_break_remaining


class LockScreen:
    """
    Full-screen lock screen that blocks computer access.

    Features:
    - Always on top, covers the whole virtual desktop
    - Cannot be closed normally
    - TimeScreen password authentication
    - Windows administrator authentication fallback
    - Starts a 10-minute grace period after unlock
    - Shutdown/restart/sleep options
    """

    def __init__(self):
        self.root = tk.Tk()
        self.cfg = ConfigManager(read_only=True)
        self.secondary_windows = []
        self._setup_window()
        self._build_ui()
        self.root.after(1000, self._periodic_safety_check)

    def _setup_window(self):
        """Configure the lock window."""
        self.root.title("Компьютер заблокирован")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#1a1a2e")

        try:
            monitors = self._get_monitor_rects()
            primary = monitors[0]
            x, y, right, bottom = primary
            self.root.geometry(f"{right - x}x{bottom - y}+{x}+{y}")
            self._create_secondary_blockers(monitors[1:])
        except Exception:
            self.root.attributes("-fullscreen", True)

        self.root.protocol("WM_DELETE_WINDOW", lambda: None)
        self.root.bind("<Alt-F4>", lambda e: "break")
        self.root.bind("<Escape>", lambda e: "break")

        try:
            icon_path = Path(__file__).parent.parent / "resources" / "icon.ico"
            if icon_path.exists():
                self.root.iconbitmap(str(icon_path))
        except Exception:
            pass

    def _get_monitor_rects(self):
        """Return monitor rectangles with the primary monitor first."""
        user32 = ctypes.windll.user32

        from ctypes import wintypes

        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", wintypes.LONG),
                ("top", wintypes.LONG),
                ("right", wintypes.LONG),
                ("bottom", wintypes.LONG),
            ]

        class MONITORINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("rcMonitor", RECT),
                ("rcWork", RECT),
                ("dwFlags", wintypes.DWORD),
            ]

        monitors = []
        monitor_enum_proc = ctypes.WINFUNCTYPE(
            wintypes.BOOL,
            wintypes.HANDLE,
            wintypes.HDC,
            ctypes.POINTER(RECT),
            wintypes.LPARAM,
        )

        def callback(hmonitor, _hdc, _rect, _data):
            info = MONITORINFO()
            info.cbSize = ctypes.sizeof(MONITORINFO)
            user32.GetMonitorInfoW(hmonitor, ctypes.byref(info))
            rect = info.rcMonitor
            monitors.append((
                bool(info.dwFlags & 1),
                (rect.left, rect.top, rect.right, rect.bottom),
            ))
            return 1

        callback_ref = monitor_enum_proc(callback)
        user32.EnumDisplayMonitors(None, None, callback_ref, 0)
        if not monitors:
            return [(0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))]

        monitors.sort(key=lambda item: not item[0])
        return [rect for _primary, rect in monitors]

    def _create_secondary_blockers(self, monitor_rects):
        """Create non-interactive blocker windows for non-primary monitors."""
        for x, y, right, bottom in monitor_rects:
            window = tk.Toplevel(self.root)
            window.overrideredirect(True)
            window.attributes("-topmost", True)
            window.configure(bg="#1a1a2e")
            window.geometry(f"{right - x}x{bottom - y}+{x}+{y}")
            window.protocol("WM_DELETE_WINDOW", lambda: None)
            window.bind("<Alt-F4>", lambda e: "break")
            window.bind("<Escape>", lambda e: "break")

            frame = tk.Frame(window, bg="#1a1a2e")
            frame.pack(expand=True)

            tk.Label(
                frame,
                text="КОМПЬЮТЕР ЗАБЛОКИРОВАН",
                font=("Arial", 34, "bold"),
                fg="#e94560",
                bg="#1a1a2e",
            ).pack(pady=(0, 18))
            tk.Label(
                frame,
                text="Разблокировка доступна на основном мониторе.",
                font=("Arial", 16),
                fg="#ffffff",
                bg="#1a1a2e",
            ).pack()

            self.secondary_windows.append(window)

    def _build_ui(self):
        """Build the lock screen UI."""
        main_frame = tk.Frame(self.root, bg="#1a1a2e")
        main_frame.pack(expand=True)

        tk.Label(
            main_frame,
            text="КОМПЬЮТЕР ЗАБЛОКИРОВАН",
            font=("Arial", 36, "bold"),
            fg="#e94560",
            bg="#1a1a2e",
        ).pack(pady=(0, 20))

        break_settings = self.cfg.get_break_settings()
        break_seconds = (
            get_active_break_remaining(os.environ.get("USERNAME", ""))
            if break_settings["enabled"] else 0
        )
        reason_text = (
            "Обязательный перерыв. Работа продолжится автоматически после его окончания."
            if break_seconds > 0
            else "Использование компьютера запрещено в это время.\nОбратитесь к администратору."
        )
        tk.Label(
            main_frame,
            text=reason_text,
            font=("Arial", 16),
            fg="#ffffff",
            bg="#1a1a2e",
            justify=tk.CENTER,
        ).pack(pady=(0, 30))

        grace_seconds = self.cfg.get_grace_remaining_seconds()
        if grace_seconds is not None:
            minutes = grace_seconds // 60
            seconds = grace_seconds % 60
            tk.Label(
                main_frame,
                text=f"Активен грейс-период: {minutes:02d}:{seconds:02d}",
                font=("Arial", 12),
                fg="#ffd700",
                bg="#1a1a2e",
            ).pack(pady=(0, 10))

        pwd_frame = tk.Frame(main_frame, bg="#1a1a2e")
        pwd_frame.pack(pady=10)

        tk.Label(
            pwd_frame,
            text="Пароль TimeScreen:",
            font=("Arial", 12),
            fg="#ffffff",
            bg="#1a1a2e",
        ).pack(side=tk.LEFT, padx=5)

        self.password_var = tk.StringVar()
        self.password_entry = tk.Entry(
            pwd_frame,
            textvariable=self.password_var,
            font=("Arial", 14),
            show="*",
            width=25,
            justify=tk.CENTER,
        )
        self.password_entry.pack(side=tk.LEFT, padx=10)
        self.password_entry.bind("<Return>", lambda e: self._check_password())
        self.password_entry.focus_set()

        self.status_label = tk.Label(
            main_frame,
            text="",
            font=("Arial", 12),
            fg="#e94560",
            bg="#1a1a2e",
        )
        self.status_label.pack(pady=5)

        tk.Button(
            main_frame,
            text="Разблокировать",
            font=("Arial", 14, "bold"),
            bg="#0f3460",
            fg="#ffffff",
            activebackground="#16213e",
            activeforeground="#ffffff",
            command=self._check_password,
            width=20,
            height=2,
            cursor="hand2",
        ).pack(pady=15)

        tk.Button(
            main_frame,
            text="Разблокировать через UAC",
            font=("Arial", 11),
            bg="#2d6a4f",
            fg="#ffffff",
            activebackground="#1b4332",
            activeforeground="#ffffff",
            command=self._windows_admin_unlock,
            width=34,
            height=1,
            cursor="hand2",
        ).pack(pady=(0, 15))

        power_frame = tk.Frame(main_frame, bg="#1a1a2e")
        power_frame.pack(pady=20)

        tk.Button(
            power_frame,
            text="Выключить",
            font=("Arial", 12),
            bg="#c0392b",
            fg="#ffffff",
            command=self._shutdown,
            width=15,
            height=2,
            cursor="hand2",
        ).grid(row=0, column=0, padx=10)

        tk.Button(
            power_frame,
            text="Перезагрузить",
            font=("Arial", 12),
            bg="#2980b9",
            fg="#ffffff",
            command=self._restart,
            width=15,
            height=2,
            cursor="hand2",
        ).grid(row=0, column=1, padx=10)

        tk.Button(
            power_frame,
            text="Сон",
            font=("Arial", 12),
            bg="#8e44ad",
            fg="#ffffff",
            command=self._sleep,
            width=15,
            height=2,
            cursor="hand2",
        ).grid(row=0, column=2, padx=10)

    def _check_password(self):
        """Verify TimeScreen password and unlock if correct."""
        password = self.password_var.get()

        ok, error = self._request_service_grace(password)
        if ok:
            self._destroy_all_windows()
            return True

        self.status_label.config(text=error or "Неверный пароль TimeScreen")
        self.password_var.set("")
        self.password_entry.focus_set()
        self._shake_window()
        return False

    def _unlock_with_grace(self):
        """Elevated path used only after Windows administrator verification."""
        self.cfg = ConfigManager(read_only=False)
        if not self.cfg.set_grace():
            self.status_label.config(text=f"Не удалось включить грейс-период: {self.cfg.last_error}")
            return False

        self._destroy_all_windows()
        return True

    @staticmethod
    def _request_service_grace(password):
        """Ask the SYSTEM service to verify the TimeScreen password."""
        try:
            import win32file
            import win32pipe
            import win32con

            win32pipe.WaitNamedPipe(SERVICE_PIPE_NAME, 3000)
            pipe = win32file.CreateFile(
                SERVICE_PIPE_NAME,
                win32con.GENERIC_READ | win32con.GENERIC_WRITE,
                0, None, win32file.OPEN_EXISTING, 0, None,
            )
            try:
                request = json.dumps({"command": "grant_grace", "password": password}).encode("utf-8")
                win32file.WriteFile(pipe, request)
                _, raw = win32file.ReadFile(pipe, 4096)
                response = json.loads(raw.decode("utf-8"))
                return bool(response.get("ok")), response.get("error", "")
            finally:
                win32file.CloseHandle(pipe)
        except Exception:
            return False, "Служба TimeScreen недоступна"

    def _destroy_all_windows(self):
        """Destroy primary and secondary lock windows."""
        for window in self.secondary_windows:
            try:
                window.destroy()
            except Exception:
                pass
        self.root.destroy()

    def _windows_admin_unlock(self):
        """Unlock via Windows UAC elevation instead of entering the TimeScreen password."""
        if self._is_current_windows_admin():
            self._unlock_with_grace()
            return

        if self._request_uac_grace():
            self.status_label.config(text="Подтвердите запрос UAC")
            self.root.after(1000, self._poll_uac_grace)
        else:
            self.status_label.config(text="Запрос UAC отменен или недоступен")

    def _is_current_windows_admin(self) -> bool:
        """Check whether the current Windows token belongs to Administrators."""
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False

    def _request_uac_grace(self) -> bool:
        """Ask Windows to run the grace helper elevated via UAC."""
        try:
            if getattr(sys, "frozen", False):
                executable = sys.executable
                parameters = "--grant-grace"
            else:
                executable = sys.executable
                main_path = Path(__file__).parent.parent / "main.py"
                parameters = f'"{main_path}" --grant-grace'

            rc = ctypes.windll.shell32.ShellExecuteW(
                None,
                "runas",
                executable,
                parameters,
                None,
                1,
            )
            return rc > 32
        except Exception:
            return False

    def _poll_uac_grace(self, attempts: int = 30):
        """Wait until the elevated helper writes grace into config."""
        cfg = ConfigManager(read_only=True)
        if cfg.is_in_grace():
            self._destroy_all_windows()
            return

        if attempts <= 0:
            self.status_label.config(text="UAC подтвержден не был или грейс-период не записался")
            return

        self.root.after(1000, lambda: self._poll_uac_grace(attempts - 1))

    def _shake_window(self):
        """Bring the window back to the front after wrong password."""
        self.root.lift()
        self.root.attributes("-topmost", True)

    def _periodic_safety_check(self):
        """Auto-close when this user is no longer subject to blocking."""
        try:
            cfg = ConfigManager(read_only=True)
            username = os.environ.get("USERNAME", "")
            break_active = (
                cfg.get_break_settings()["enabled"]
                and get_active_break_remaining(username) > 0
            )
            should_block = cfg.should_block_user(username) or (
                cfg.is_enabled() and cfg.is_controlled_user(username)
                and not cfg.is_in_grace() and break_active
            )
            if not should_block:
                self._destroy_all_windows()
                return
            self.root.lift()
            self.root.attributes("-topmost", True)
            for window in self.secondary_windows:
                window.lift()
                window.attributes("-topmost", True)
        except tk.TclError:
            return
        self.root.after(3000, self._periodic_safety_check)

    def _shutdown(self):
        """Shutdown computer."""
        if messagebox.askyesno("Подтверждение", "Вы действительно хотите выключить компьютер?", parent=self.root):
            subprocess.run(["shutdown", "/s", "/t", "0"], capture_output=True)

    def _restart(self):
        """Restart computer."""
        if messagebox.askyesno("Подтверждение", "Вы действительно хотите перезагрузить компьютер?", parent=self.root):
            subprocess.run(["shutdown", "/r", "/t", "0"], capture_output=True)

    def _sleep(self):
        """Put computer to sleep."""
        if messagebox.askyesno("Подтверждение", "Перевести компьютер в спящий режим?", parent=self.root):
            subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState,0,0,1"], capture_output=True)

    def run(self):
        """Start the lock screen."""
        self.root.mainloop()


def run_lock_screen():
    """Entry point for running lock screen from command line (--locker-mode)."""
    lock = LockScreen()
    lock.run()


def show_lock_screen():
    """Convenience function to show lock screen."""
    run_lock_screen()


if __name__ == "__main__":
    run_lock_screen()
