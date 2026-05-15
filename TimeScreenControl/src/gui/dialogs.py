"""
TimeScreen Control - Dialog Windows
Password dialogs, confirmation dialogs, etc.
"""

import tkinter as tk
from tkinter import ttk, simpledialog, messagebox
from typing import Optional


class PasswordDialog(simpledialog.Toplevel):
    """Password entry dialog for admin authentication."""
    
    def __init__(self, parent, title: str = "Вход в настройки", verify_func=None):
        super().__init__(parent)
        self.title(title)
        self.result: Optional[str] = None
        self.verify_func = verify_func
        
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)
        
        # Center on parent
        self.geometry("+%d+%d" % (
            parent.winfo_rootx() + 50,
            parent.winfo_rooty() + 50
        ))
        
        self._build_ui()
        self.wait_window(self)
    
    def _build_ui(self):
        main_frame = ttk.Frame(self, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Icon/Title
        title_label = ttk.Label(
            main_frame,
            text="🔐 Требуется пароль администратора",
            font=("Arial", 12, "bold")
        )
        title_label.pack(pady=(0, 15))
        
        # Password entry
        entry_frame = ttk.Frame(main_frame)
        entry_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(entry_frame, text="Пароль:").pack(side=tk.LEFT)
        
        self.password_var = tk.StringVar()
        self.password_entry = ttk.Entry(
            entry_frame,
            textvariable=self.password_var,
            show="*",
            width=30
        )
        self.password_entry.pack(side=tk.LEFT, padx=10)
        self.password_entry.bind("<Return>", lambda e: self._ok())
        self.password_entry.focus_set()
        
        # Status label
        self.status_label = ttk.Label(
            main_frame,
            text="",
            foreground="red"
        )
        self.status_label.pack(pady=5)
        
        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=15)
        
        ttk.Button(btn_frame, text="OK", command=self._ok).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Отмена", command=self._cancel).pack(side=tk.RIGHT)
    
    def _ok(self):
        password = self.password_var.get()
        
        if not password:
            self.status_label.config(text="Введите пароль")
            return
        
        if self.verify_func:
            if not self.verify_func(password):
                self.status_label.config(text="Неверный пароль!")
                self.password_var.set("")
                self.password_entry.focus_set()
                return
        
        self.result = password
        self.destroy()
    
    def _cancel(self):
        self.destroy()


class SetPasswordDialog(simpledialog.Toplevel):
    """Dialog for setting a new password."""
    
    def __init__(self, parent, title: str = "Установка пароля"):
        super().__init__(parent)
        self.title(title)
        self.result: Optional[str] = None
        
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)
        
        # Center on parent
        self.geometry("+%d+%d" % (
            parent.winfo_rootx() + 50,
            parent.winfo_rooty() + 50
        ))
        
        self._build_ui()
        self.wait_window(self)
    
    def _build_ui(self):
        main_frame = ttk.Frame(self, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title
        title_label = ttk.Label(
            main_frame,
            text="🔒 Установка пароля администратора",
            font=("Arial", 12, "bold")
        )
        title_label.pack(pady=(0, 10))
        
        info_label = ttk.Label(
            main_frame,
            text="Пароль должен быть минимум 4 символа.\nЗапишите его в надёжном месте!",
            justify=tk.CENTER
        )
        info_label.pack(pady=(0, 15))
        
        # Password entries
        entry_frame = ttk.Frame(main_frame)
        entry_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(entry_frame, text="Пароль:", width=15).grid(row=0, column=0, sticky=tk.W)
        self.password_var = tk.StringVar()
        self.password_entry = ttk.Entry(
            entry_frame,
            textvariable=self.password_var,
            show="*",
            width=30
        )
        self.password_entry.grid(row=0, column=1, padx=10, pady=5)
        
        ttk.Label(entry_frame, text="Подтвердите:", width=15).grid(row=1, column=0, sticky=tk.W)
        self.confirm_var = tk.StringVar()
        self.confirm_entry = ttk.Entry(
            entry_frame,
            textvariable=self.confirm_var,
            show="*",
            width=30
        )
        self.confirm_entry.grid(row=1, column=1, padx=10, pady=5)
        self.confirm_entry.bind("<Return>", lambda e: self._ok())
        
        # Status label
        self.status_label = ttk.Label(
            main_frame,
            text="",
            foreground="red"
        )
        self.status_label.pack(pady=10)
        
        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(btn_frame, text="OK", command=self._ok).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Отмена", command=self._cancel).pack(side=tk.RIGHT)
        
        self.password_entry.focus_set()
    
    def _ok(self):
        password = self.password_var.get()
        confirm = self.confirm_var.get()
        
        if len(password) < 4:
            self.status_label.config(text="Пароль должен быть минимум 4 символа")
            return
        
        if password != confirm:
            self.status_label.config(text="Пароли не совпадают")
            self.confirm_var.set("")
            self.confirm_entry.focus_set()
            return
        
        self.result = password
        self.destroy()
    
    def _cancel(self):
        self.destroy()


class ConfirmDialog(messagebox.Message):
    """Simple confirmation dialog."""
    
    @staticmethod
    def ask(parent, title: str, message: str) -> bool:
        result = messagebox.askyesno(title, message, parent=parent)
        return result is True
