"""
TimeScreen Control - Main Settings Application
Complete GUI for managing parental control settings.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import sys
import os
from pathlib import Path
from typing import Optional

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.manager import ConfigManager
from config.security import hash_password
from gui.dialogs import PasswordDialog, SetPasswordDialog, ConfirmDialog
from gui.components.user_selector import UserSelector
from gui.components.interval_editor import IntervalEditor
from gui.timer_overlay import TimerOverlay


class SettingsApp:
    """
    Main settings application window.
    
    Features:
    - Single password entry on startup (if password is set)
    - Force password setup if not set
    - All settings in one place
    - Clean, modern UI
    - Protection toggle
    - User selection
    - Interval management
    - Timer overlay preview
    """
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("TimeScreen Control - Настройки")
        self.root.geometry("800x700")
        self.root.minsize(700, 600)
        
        # Try to load icon
        try:
            icon_path = Path(__file__).parent / "resources" / "icon.ico"
            if icon_path.exists():
                self.root.iconbitmap(str(icon_path))
        except Exception:
            pass
        
        # Initialize config
        self.cfg = ConfigManager(read_only=False)
        
        # Authentication state
        self.authenticated = False
        self.admin_password_set = self.cfg.has_password()
        
        # Timer overlay reference
        self.timer_overlay: Optional[TimerOverlay] = None
        
        # Center window
        self._center_window()
        
        # Authenticate or setup password
        if not self._authenticate_or_setup():
            self.root.after(100, self.root.destroy)
            return
        
        self._build_ui()
        
        # Start timer overlay if enabled
        if self.cfg.show_timer() and self.cfg.is_enabled():
            self.root.after(500, self._start_timer_overlay)
    
    def _center_window(self):
        """Center window on screen."""
        self.root.update_idletasks()
        width = 800
        height = 700
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")
    
    def _authenticate_or_setup(self) -> bool:
        """
        Authenticate user or force password setup.
        
        Returns:
            True if successful, False if user cancelled
        """
        if not self.admin_password_set:
            # No password set - force setup
            result = messagebox.askyesnocancel(
                "Первый запуск",
                "Пароль администратора не установлен.\n\n"
                "Хотите установить пароль сейчас?\n"
                "Без пароля настройки не будут защищены.",
                parent=self.root
            )
            
            if result is None:  # Cancel
                return False
            
            if result:  # Yes
                dialog = SetPasswordDialog(self.root, "Установка пароля администратора")
                if dialog.result:
                    if self.cfg.set_password(dialog.result):
                        self.authenticated = True
                        self.admin_password_set = True
                        messagebox.showinfo(
                            "Успешно",
                            "Пароль установлен!\nЗапомните его - без пароля вы не сможете изменить настройки.",
                            parent=self.root
                        )
                    else:
                        messagebox.showerror("Ошибка", "Не удалось сохранить пароль", parent=self.root)
                        return False
                else:
                    return False
            else:  # No - proceed without password
                self.authenticated = True
        else:
            # Password exists - require authentication
            dialog = PasswordDialog(self.root, verify_func=self.cfg.verify_password)
            if dialog.result:
                self.authenticated = True
            else:
                return False
        
        return True
    
    def _build_ui(self):
        """Build the main UI."""
        # Main container with notebook
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Tab 1: General Settings
        general_frame = ttk.Frame(notebook, padding=20)
        notebook.add(general_frame, text="📋 Общие")
        self._build_general_tab(general_frame)
        
        # Tab 2: Users
        users_frame = ttk.Frame(notebook, padding=20)
        notebook.add(users_frame, text="👥 Пользователи")
        self._build_users_tab(users_frame)
        
        # Tab 3: Time Intervals
        intervals_frame = ttk.Frame(notebook, padding=20)
        notebook.add(intervals_frame, text="⏰ Временные интервалы")
        self._build_intervals_tab(intervals_frame)
        
        # Tab 4: Timer Overlay
        timer_frame = ttk.Frame(notebook, padding=20)
        notebook.add(timer_frame, text="⏱️ Таймер")
        self._build_timer_tab(timer_frame)
        
        # Status bar
        self.status_var = tk.StringVar(value="Готово")
        status_bar = ttk.Label(
            self.root,
            textvariable=self.status_var,
            relief=tk.SUNKEN,
            anchor=tk.W
        )
        status_bar.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        # Update status
        self._update_status()
    
    def _build_general_tab(self, parent):
        """Build general settings tab."""
        # Title
        title = ttk.Label(
            parent,
            text="Общие настройки защиты",
            font=("Arial", 16, "bold")
        )
        title.pack(pady=(0, 20))
        
        # Protection toggle
        protection_frame = ttk.LabelFrame(parent, text="Состояние защиты", padding=15)
        protection_frame.pack(fill=tk.X, pady=10)
        
        self.enabled_var = tk.BooleanVar(value=self.cfg.is_enabled())
        
        toggle_btn = ttk.Checkbutton(
            protection_frame,
            text="✅ Защита включена",
            variable=self.enabled_var,
            command=self._toggle_protection
        )
        toggle_btn.pack(pady=5)
        
        info_label = ttk.Label(
            protection_frame,
            text="Когда защита включена, служба блокирует компьютер\nвне разрешённых временных интервалов",
            foreground="blue",
            justify=tk.CENTER
        )
        info_label.pack(pady=10)
        
        # Password management
        pwd_frame = ttk.LabelFrame(parent, text="Пароль администратора", padding=15)
        pwd_frame.pack(fill=tk.X, pady=10)
        
        pwd_status = "✅ Установлен" if self.admin_password_set else "❌ Не установлен"
        pwd_color = "green" if self.admin_password_set else "red"
        
        ttk.Label(
            pwd_frame,
            text=f"Статус: {pwd_status}",
            foreground=pwd_color
        ).pack(pady=5)
        
        btn_frame = ttk.Frame(pwd_frame)
        btn_frame.pack(pady=10)
        
        ttk.Button(
            btn_frame,
            text="🔑 Изменить пароль",
            command=self._change_password
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            btn_frame,
            text="🗑️ Удалить пароль",
            command=self._remove_password
        ).pack(side=tk.LEFT, padx=5)
        
        # Info section
        info_box = ttk.LabelFrame(parent, text="ℹ️ Информация", padding=15)
        info_box.pack(fill=tk.BOTH, expand=True, pady=10)
        
        controlled_count = len(self.cfg.get_controlled_users())
        intervals_count = len(self.cfg.get_intervals())
        
        info_text = f"""
Статус защиты: {'ВКЛЮЧЕНА' if self.cfg.is_enabled() else 'ВЫКЛЮЧЕНА'}
Контролируемых пользователей: {controlled_count if controlled_count > 0 else 'ВСЕ'}
Временных интервалов: {intervals_count}
Таймер отображается: {'Да' if self.cfg.show_timer() else 'Нет'}
        """.strip()
        
        ttk.Label(info_box, text=info_text, justify=tk.LEFT).pack(anchor=tk.W)
    
    def _build_users_tab(self, parent):
        """Build users management tab."""
        user_selector = UserSelector(parent, self.cfg)
        user_selector.pack(fill=tk.BOTH, expand=True)
    
    def _build_intervals_tab(self, parent):
        """Build time intervals management tab."""
        # Title
        title = ttk.Label(
            parent,
            text="Разрешённые временные интервалы",
            font=("Arial", 16, "bold")
        )
        title.pack(pady=(0, 10))
        
        info_label = ttk.Label(
            parent,
            text="В эти промежутки времени использование компьютера РАЗРЕШЕНО",
            foreground="blue"
        )
        info_label.pack(pady=(0, 15))
        
        # List frame
        list_frame = ttk.Frame(parent)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Create treeview for intervals
        columns = ("days", "start", "end")
        self.intervals_tree = ttk.Treeview(
            list_frame,
            columns=columns,
            show="headings",
            height=10
        )
        
        self.intervals_tree.heading("days", text="Дни недели")
        self.intervals_tree.heading("start", text="Начало")
        self.intervals_tree.heading("end", text="Конец")
        
        self.intervals_tree.column("days", width=300)
        self.intervals_tree.column("start", width=100)
        self.intervals_tree.column("end", width=100)
        
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.intervals_tree.yview)
        self.intervals_tree.configure(yscrollcommand=scrollbar.set)
        
        self.intervals_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Bind double-click to edit
        self.intervals_tree.bind("<Double-1>", self._edit_interval)
        
        # Buttons
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(
            btn_frame,
            text="➕ Добавить интервал",
            command=self._add_interval
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            btn_frame,
            text="✏️ Изменить",
            command=self._edit_interval
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            btn_frame,
            text="🗑️ Удалить",
            command=self._delete_interval
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            btn_frame,
            text="🗑️ Удалить все",
            command=self._clear_all_intervals
        ).pack(side=tk.RIGHT, padx=5)
        
        # Load intervals
        self._load_intervals()
    
    def _build_timer_tab(self, parent):
        """Build timer overlay settings tab."""
        # Title
        title = ttk.Label(
            parent,
            text="Настройки таймера оставшегося времени",
            font=("Arial", 16, "bold")
        )
        title.pack(pady=(0, 10))
        
        # Preview
        preview_frame = ttk.LabelFrame(parent, text="Предпросмотр", padding=20)
        preview_frame.pack(fill=tk.X, pady=10)
        
        preview_label = tk.Label(
            preview_frame,
            text="🔒 01:23:45",
            font=("Consolas", 24, "bold"),
            fg="#ff6b6b",
            bg="#1a1a2e",
            padx=20,
            pady=10
        )
        preview_label.pack()
        
        ttk.Label(
            preview_frame,
            text="Таймер можно перетаскивать мышью\nПравый клик для меню",
            justify=tk.CENTER
        ).pack(pady=10)
        
        # Settings
        settings_frame = ttk.LabelFrame(parent, text="Настройки отображения", padding=15)
        settings_frame.pack(fill=tk.X, pady=10)
        
        self.show_timer_var = tk.BooleanVar(value=self.cfg.show_timer())
        
        show_chk = ttk.Checkbutton(
            settings_frame,
            text="Показывать таймер на рабочем столе",
            variable=self.show_timer_var,
            command=self._toggle_timer_visibility
        )
        show_chk.pack(pady=5)
        
        btn_frame = ttk.Frame(settings_frame)
        btn_frame.pack(pady=10)
        
        ttk.Button(
            btn_frame,
            text="🔄 Сбросить позицию",
            command=self._reset_timer_position
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            btn_frame,
            text="👁️ Предварительный просмотр",
            command=self._preview_timer
        ).pack(side=tk.LEFT, padx=5)
    
    def _load_intervals(self):
        """Load intervals into treeview."""
        # Clear existing items
        for item in self.intervals_tree.get_children():
            self.intervals_tree.delete(item)
        
        # Load from config
        day_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        
        for interval in self.cfg.get_intervals():
            days = interval.get("days", [])
            days_str = ", ".join(day_names[d] for d in sorted(days))
            start = interval.get("start", "00:00")
            end = interval.get("end", "00:00")
            
            self.intervals_tree.insert("", tk.END, values=(days_str, start, end))
    
    def _toggle_protection(self):
        """Toggle protection enable/disable."""
        new_state = self.enabled_var.get()
        
        if self.cfg.set_enabled(new_state):
            status = "включена" if new_state else "выключена"
            self.status_var.set(f"Защита {status}")
            self._update_status()
            
            # Update timer overlay
            if new_state and self.cfg.show_timer():
                self._start_timer_overlay()
            elif not new_state and self.timer_overlay:
                self.timer_overlay.destroy()
                self.timer_overlay = None
        else:
            messagebox.showerror("Ошибка", "Не удалось изменить состояние защиты", parent=self.root)
            self.enabled_var.set(not new_state)
    
    def _change_password(self):
        """Change admin password."""
        # First verify current password
        dialog = PasswordDialog(self.root, "Подтверждение пароля", verify_func=self.cfg.verify_password)
        if not dialog.result:
            return
        
        # Now set new password
        new_dialog = SetPasswordDialog(self.root, "Новый пароль")
        if new_dialog.result:
            if self.cfg.set_password(new_dialog.result):
                messagebox.showinfo("Успешно", "Пароль изменён", parent=self.root)
                self.status_var.set("Пароль изменён")
            else:
                messagebox.showerror("Ошибка", "Не удалось сохранить пароль", parent=self.root)
    
    def _remove_password(self):
        """Remove admin password."""
        if not ConfirmDialog.ask(
            self.root,
            "Подтверждение",
            "Вы уверены, что хотите удалить пароль?\nНастройки станут незащищёнными!"
        ):
            return
        
        # Verify current password first
        dialog = PasswordDialog(self.root, "Подтверждение", verify_func=self.cfg.verify_password)
        if not dialog.result:
            return
        
        # Clear password
        self.cfg.config["password_hash"] = None
        if self.cfg.save():
            self.admin_password_set = False
            messagebox.showinfo("Успешно", "Пароль удалён", parent=self.root)
            self._update_status()
        else:
            messagebox.showerror("Ошибка", "Не удалось удалить пароль", parent=self.root)
    
    def _add_interval(self):
        """Add new time interval."""
        dialog = IntervalEditor(self.root)
        if dialog.result:
            if self.cfg.add_interval(
                dialog.result["start"],
                dialog.result["end"],
                dialog.result["days"]
            ):
                self._load_intervals()
                self.status_var.set("Интервал добавлен")
            else:
                messagebox.showerror("Ошибка", "Не удалось добавить интервал", parent=self.root)
    
    def _edit_interval(self, event=None):
        """Edit selected interval."""
        selection = self.intervals_tree.selection()
        if not selection:
            messagebox.showwarning("Предупреждение", "Выберите интервал для редактирования", parent=self.root)
            return
        
        index = self.intervals_tree.index(selection[0])
        intervals = self.cfg.get_intervals()
        
        if 0 <= index < len(intervals):
            dialog = IntervalEditor(self.root, intervals[index])
            if dialog.result:
                # Remove old and add new
                self.cfg.remove_interval(index)
                if self.cfg.add_interval(
                    dialog.result["start"],
                    dialog.result["end"],
                    dialog.result["days"]
                ):
                    self._load_intervals()
                    self.status_var.set("Интервал обновлён")
                else:
                    messagebox.showerror("Ошибка", "Не удалось обновить интервал", parent=self.root)
    
    def _delete_interval(self):
        """Delete selected interval."""
        selection = self.intervals_tree.selection()
        if not selection:
            messagebox.showwarning("Предупреждение", "Выберите интервал для удаления", parent=self.root)
            return
        
        if not ConfirmDialog.ask(
            self.root,
            "Подтверждение",
            "Удалить выбранный интервал?"
        ):
            return
        
        index = self.intervals_tree.index(selection[0])
        if self.cfg.remove_interval(index):
            self._load_intervals()
            self.status_var.set("Интервал удалён")
        else:
            messagebox.showerror("Ошибка", "Не удалось удалить интервал", parent=self.root)
    
    def _clear_all_intervals(self):
        """Clear all intervals."""
        if not ConfirmDialog.ask(
            self.root,
            "Подтверждение",
            "Удалить ВСЕ временные интервалы?\nКомпьютер будет доступен всегда!"
        ):
            return
        
        if self.cfg.clear_intervals():
            self._load_intervals()
            self.status_var.set("Все интервалы удалены")
        else:
            messagebox.showerror("Ошибка", "Не удалось очистить интервалы", parent=self.root)
    
    def _toggle_timer_visibility(self):
        """Toggle timer overlay visibility."""
        show = self.show_timer_var.get()
        
        if self.cfg.set_show_timer(show):
            if show:
                self._start_timer_overlay()
            else:
                if self.timer_overlay:
                    self.timer_overlay.destroy()
                    self.timer_overlay = None
            self._update_status()
        else:
            messagebox.showerror("Ошибка", "Не удалось изменить настройку", parent=self.root)
            self.show_timer_var.set(not show)
    
    def _reset_timer_position(self):
        """Reset timer position to default."""
        if self.cfg.set_timer_position(100, 100):
            if self.timer_overlay and self.timer_overlay.window:
                self.timer_overlay.window.geometry("+100+100")
            self.status_var.set("Позиция таймера сброшена")
        else:
            messagebox.showerror("Ошибка", "Не удалось сбросить позицию", parent=self.root)
    
    def _preview_timer(self):
        """Preview timer overlay."""
        if not self.timer_overlay:
            self._start_timer_overlay()
        
        if self.timer_overlay:
            self.timer_overlay.show()
    
    def _start_timer_overlay(self):
        """Start timer overlay."""
        if not self.cfg.show_timer() or not self.cfg.is_enabled():
            return
        
        if self.timer_overlay is None:
            self.timer_overlay = TimerOverlay(self.root, self.cfg)
            self.timer_overlay.create()
            self.timer_overlay.start_updates()
    
    def _update_status(self):
        """Update status information."""
        protected = "ВКЛЮЧЕНА" if self.cfg.is_enabled() else "ВЫКЛЮЧЕНА"
        users = self.cfg.get_controlled_users()
        users_str = f"{len(users)} пользователей" if users else "ВСЕ пользователи"
        
        self.status_var.set(f"Защита: {protected} | {users_str}")
    
    def run(self):
        """Start the application."""
        self.root.mainloop()
        
        # Cleanup
        if self.timer_overlay:
            self.timer_overlay.destroy()


def main():
    """Main entry point for settings app."""
    app = SettingsApp()
    app.run()


if __name__ == "__main__":
    main()
