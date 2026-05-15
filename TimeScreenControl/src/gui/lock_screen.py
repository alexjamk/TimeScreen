"""
TimeScreen Control - Lock Screen
Full-screen blocking window with password authentication.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.manager import ConfigManager


class LockScreen:
    """
    Full-screen lock screen that blocks computer access.
    
    Features:
    - Always on top, full screen
    - Cannot be closed normally
    - Password authentication to unlock
    - Shutdown/restart options
    - Grace period support
    """
    
    def __init__(self):
        self.root = tk.Tk()
        self.cfg = ConfigManager(read_only=True)
        self._setup_window()
        self._build_ui()
    
    def _setup_window(self):
        """Configure the lock window."""
        self.root.title("Компьютер заблокирован")
        self.root.attributes("-fullscreen", True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#1a1a2e")
        
        # Prevent closing
        self.root.protocol("WM_DELETE_WINDOW", lambda: None)
        
        # Try to load icon
        try:
            icon_path = Path(__file__).parent.parent / "resources" / "icon.ico"
            if icon_path.exists():
                self.root.iconbitmap(str(icon_path))
        except Exception:
            pass
    
    def _build_ui(self):
        """Build the lock screen UI."""
        # Main frame for centering
        main_frame = tk.Frame(self.root, bg="#1a1a2e")
        main_frame.pack(expand=True)
        
        # Title
        title_label = tk.Label(
            main_frame,
            text="🔒 КОМПЬЮТЕР ЗАБЛОКИРОВАН",
            font=("Arial", 36, "bold"),
            fg="#e94560",
            bg="#1a1a2e"
        )
        title_label.pack(pady=(0, 20))
        
        # Info message
        info_label = tk.Label(
            main_frame,
            text="Использование компьютера запрещено в это время.\nОбратитесь к администратору.",
            font=("Arial", 16),
            fg="#ffffff",
            bg="#1a1a2e",
            justify=tk.CENTER
        )
        info_label.pack(pady=(0, 30))
        
        # Grace period notice
        if self.cfg.is_in_grace():
            grace_label = tk.Label(
                main_frame,
                text="⏰ Активен льготный период (10 минут)",
                font=("Arial", 12),
                fg="#ffd700",
                bg="#1a1a2e"
            )
            grace_label.pack(pady=(0, 10))
        
        # Password entry
        pwd_frame = tk.Frame(main_frame, bg="#1a1a2e")
        pwd_frame.pack(pady=10)
        
        tk.Label(
            pwd_frame,
            text="Пароль администратора:",
            font=("Arial", 12),
            fg="#ffffff",
            bg="#1a1a2e"
        ).pack(side=tk.LEFT, padx=5)
        
        self.password_var = tk.StringVar()
        self.password_entry = tk.Entry(
            pwd_frame,
            textvariable=self.password_var,
            font=("Arial", 14),
            show="*",
            width=25,
            justify=tk.CENTER
        )
        self.password_entry.pack(side=tk.LEFT, padx=10)
        self.password_entry.bind("<Return>", lambda e: self._check_password())
        self.password_entry.focus_set()
        
        # Status label
        self.status_label = tk.Label(
            main_frame,
            text="",
            font=("Arial", 12),
            fg="#e94560",
            bg="#1a1a2e"
        )
        self.status_label.pack(pady=5)
        
        # Unlock button
        unlock_btn = tk.Button(
            main_frame,
            text="🔓 Разблокировать",
            font=("Arial", 14, "bold"),
            bg="#0f3460",
            fg="#ffffff",
            activebackground="#16213e",
            activeforeground="#ffffff",
            command=self._check_password,
            width=20,
            height=2,
            cursor="hand2"
        )
        unlock_btn.pack(pady=15)
        
        # Power buttons frame
        power_frame = tk.Frame(main_frame, bg="#1a1a2e")
        power_frame.pack(pady=20)
        
        # Shutdown button
        shutdown_btn = tk.Button(
            power_frame,
            text="⏻ Выключить",
            font=("Arial", 12),
            bg="#c0392b",
            fg="#ffffff",
            command=self._shutdown,
            width=15,
            height=2,
            cursor="hand2"
        )
        shutdown_btn.grid(row=0, column=0, padx=10)
        
        # Restart button
        restart_btn = tk.Button(
            power_frame,
            text="🔄 Перезагрузить",
            font=("Arial", 12),
            bg="#2980b9",
            fg="#ffffff",
            command=self._restart,
            width=15,
            height=2,
            cursor="hand2"
        )
        restart_btn.grid(row=0, column=1, padx=10)
        
        # Sleep button
        sleep_btn = tk.Button(
            power_frame,
            text="💤 Сон",
            font=("Arial", 12),
            bg="#8e44ad",
            fg="#ffffff",
            command=self._sleep,
            width=15,
            height=2,
            cursor="hand2"
        )
        sleep_btn.grid(row=0, column=2, padx=10)
    
    def _check_password(self):
        """Verify password and unlock if correct."""
        password = self.password_var.get()
        
        if self.cfg.verify_password(password):
            # Clear grace period on successful unlock
            self.cfg.clear_grace()
            self.root.destroy()
            return True
        else:
            self.status_label.config(text="❌ Неверный пароль!")
            self.password_var.set("")
            self.password_entry.focus_set()
            
            # Shake animation for wrong password
            self._shake_window()
            return False
    
    def _shake_window(self):
        """Shake window to indicate wrong password."""
        for i in range(5):
            offset = 10 if i % 2 == 0 else -10
            x = self.root.winfo_x() + offset
            self.root.geometry(f"+{x}+{self.root.winfo_y()}")
            self.root.after(50)
        
        # Reset position
        self.root.attributes("-fullscreen", True)
    
    def _shutdown(self):
        """Shutdown computer."""
        if messagebox.askyesno(
            "Подтверждение",
            "Вы действительно хотите выключить компьютер?",
            parent=self.root
        ):
            subprocess.run(
                ["shutdown", "/s", "/t", "0"],
                capture_output=True
            )
    
    def _restart(self):
        """Restart computer."""
        if messagebox.askyesno(
            "Подтверждение",
            "Вы действительно хотите перезагрузить компьютер?",
            parent=self.root
        ):
            subprocess.run(
                ["shutdown", "/r", "/t", "0"],
                capture_output=True
            )
    
    def _sleep(self):
        """Put computer to sleep."""
        if messagebox.askyesno(
            "Подтверждение",
            "Перевести компьютер в спящий режим?",
            parent=self.root
        ):
            subprocess.run(
                ["rundll32.exe", "powrprof.dll,SetSuspendState,0,0,1"],
                capture_output=True
            )
    
    def run(self):
        """Start the lock screen."""
        self.root.mainloop()


def show_lock_screen():
    """Convenience function to show lock screen."""
    lock = LockScreen()
    lock.run()


if __name__ == "__main__":
    show_lock_screen()
