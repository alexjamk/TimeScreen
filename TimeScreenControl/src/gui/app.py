"""
TimeScreen Control - Main Settings Application
Complete GUI for managing parental control settings.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import sys
import os
import subprocess
from pathlib import Path
from typing import Optional

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.manager import ConfigManager
from config.paths import AGENT_PID
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
            icon_path = Path(__file__).parent.parent / "resources" / "icon.ico"
            if icon_path.exists():
                self.root.iconbitmap(str(icon_path))
        except Exception:
            pass
        
        # Initialize config
        self.cfg = ConfigManager(read_only=False)
        self.timer_overlay: Optional[TimerOverlay] = None
        if self.cfg.config.get("_tampered"):
            messagebox.showerror(
                "Конфигурация повреждена",
                "Настройки заблокированы: " + self.cfg.config.get("_tamper_reason", "неверная подпись"),
                parent=self.root,
            )
            self.root.after(100, self.root.destroy)
            return
        
        # Authentication state
        self.authenticated = False
        self.admin_password_set = self.cfg.has_password()
        
        # Center window
        self._center_window()
        
        # Authenticate or setup password
        if not self._authenticate_or_setup():
            self.root.after(100, self.root.destroy)
            return
        
        self._build_ui()
        
        # Start timer overlay if enabled
        if self.cfg.show_timer() and self.cfg.is_enabled():
            self.root.after(500, self._start_timer_process)
    
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
            result = messagebox.askokcancel(
                "Первый запуск",
                "Пароль администратора не установлен.\n\n"
                "Для защиты настроек необходимо установить пароль.",
                parent=self.root
            )
            
            if not result:
                return False
            dialog = SetPasswordDialog(self.root, "Установка пароля администратора")
            if dialog.result and self.cfg.set_password(dialog.result):
                self.authenticated = True
                self.admin_password_set = True
                messagebox.showinfo(
                    "Успешно", "Пароль установлен. Запомните его.", parent=self.root
                )
            else:
                if dialog.result:
                    messagebox.showerror("Ошибка", self.cfg.last_error or "Не удалось сохранить пароль", parent=self.root)
                return False
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
        
        # Tab 4: Mandatory breaks
        breaks_frame = ttk.Frame(notebook, padding=20)
        notebook.add(breaks_frame, text="☕ Перерывы")
        self._build_breaks_tab(breaks_frame)

        # Tab 5: Timer Overlay
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
        
        # Info section
        info_box = ttk.LabelFrame(parent, text="ℹ️ Информация", padding=15)
        info_box.pack(fill=tk.BOTH, expand=True, pady=10)
        
        self.info_var = tk.StringVar()
        ttk.Label(info_box, textvariable=self.info_var, justify=tk.LEFT).pack(anchor=tk.W)
    
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

    def _build_breaks_tab(self, parent):
        """Build optional recurring work/break cycle settings."""
        settings = self.cfg.get_break_settings()
        ttk.Label(
            parent,
            text="Регулярные перерывы",
            font=("Arial", 16, "bold"),
        ).pack(pady=(0, 12))
        ttk.Label(
            parent,
            text=(
                "Считается только фактическое разрешённое время активной выбранной учётной записи.\n"
                "Сон, выключение, другая учётная запись и время блокировки не засчитываются."
            ),
            foreground="blue",
            justify=tk.CENTER,
        ).pack(pady=(0, 18))

        settings_frame = ttk.LabelFrame(parent, text="Цикл работы и отдыха", padding=20)
        settings_frame.pack(fill=tk.X, pady=10)
        self.break_enabled_var = tk.BooleanVar(value=settings["enabled"])
        self.work_duration_var = tk.StringVar(value=str(settings["work_minutes"]))
        self.break_duration_var = tk.StringVar(value=str(settings["break_minutes"]))

        ttk.Checkbutton(
            settings_frame,
            text="Включить обязательные перерывы",
            variable=self.break_enabled_var,
        ).grid(row=0, column=0, columnspan=3, sticky=tk.W, pady=(0, 15))

        ttk.Label(settings_frame, text="Работать").grid(row=1, column=0, sticky=tk.W, pady=6)
        ttk.Spinbox(
            settings_frame,
            from_=1,
            to=1440,
            width=8,
            textvariable=self.work_duration_var,
        ).grid(row=1, column=1, padx=8, pady=6)
        ttk.Label(settings_frame, text="минут до перерыва").grid(row=1, column=2, sticky=tk.W, pady=6)

        ttk.Label(settings_frame, text="Перерыв").grid(row=2, column=0, sticky=tk.W, pady=6)
        ttk.Spinbox(
            settings_frame,
            from_=1,
            to=180,
            width=8,
            textvariable=self.break_duration_var,
        ).grid(row=2, column=1, padx=8, pady=6)
        ttk.Label(settings_frame, text="минут").grid(row=2, column=2, sticky=tk.W, pady=6)

        ttk.Button(
            settings_frame,
            text="💾 Сохранить настройки перерывов",
            command=self._save_break_settings,
        ).grid(row=3, column=0, columnspan=3, pady=(18, 4))

        ttk.Label(
            parent,
            text=(
                "Перед перерывом выбранный пользователь увидит уведомления за 10, 5 и 1 минуту.\n"
                "Изменение параметров или повторное включение начинает новый рабочий цикл."
            ),
            justify=tk.CENTER,
        ).pack(pady=18)

    def _save_break_settings(self):
        try:
            work_minutes = int(self.work_duration_var.get())
            break_minutes = int(self.break_duration_var.get())
        except ValueError:
            messagebox.showerror("Ошибка", "Введите целое количество минут", parent=self.root)
            return
        if self.cfg.set_break_settings(
            self.break_enabled_var.get(), break_minutes, work_minutes
        ):
            self.status_var.set("Настройки перерывов сохранены")
            self._update_status()
        else:
            messagebox.showerror(
                "Ошибка",
                self.cfg.last_error or "Не удалось сохранить настройки перерывов",
                parent=self.root,
            )
    
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
                self.cfg.set_show_timer(True)
                self._start_timer_process()
            elif not new_state:
                if self.timer_overlay:
                    self.timer_overlay.destroy()
                    self.timer_overlay = None
                self._stop_timer_process()
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
                self._update_status()
            else:
                detail = f"\n\n{self.cfg.last_error}" if getattr(self.cfg, "last_error", "") else ""
                messagebox.showerror("Ошибка", f"Не удалось добавить интервал{detail}", parent=self.root)
    
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
                if self.cfg.replace_interval(
                    index,
                    dialog.result["start"],
                    dialog.result["end"],
                    dialog.result["days"]
                ):
                    self._load_intervals()
                    self.status_var.set("Интервал обновлён")
                    self._update_status()
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
            self._update_status()
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
            self._update_status()
        else:
            messagebox.showerror("Ошибка", "Не удалось очистить интервалы", parent=self.root)
    
    def _toggle_timer_visibility(self):
        """Toggle timer overlay visibility."""
        show = self.show_timer_var.get()
        
        if self.cfg.set_show_timer(show):
            if show:
                self._start_timer_process()
            else:
                if self.timer_overlay:
                    self.timer_overlay.destroy()
                    self.timer_overlay = None
                self._stop_timer_process()
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
        if self.timer_overlay is None:
            self.timer_overlay = TimerOverlay(self.root, self.cfg)
            self.timer_overlay.create()
        
        if self.timer_overlay:
            self.timer_overlay.show()
            self.timer_overlay.start_preview()
    
    def _start_timer_overlay(self):
        """Start timer overlay."""
        if not self.cfg.show_timer() or not self.cfg.is_enabled():
            return
        
        if self.timer_overlay is None:
            self.timer_overlay = TimerOverlay(self.root, self.cfg)
            self.timer_overlay.create()

        self.timer_overlay.show()
        self.timer_overlay.start_updates()

    def _start_timer_process(self):
        """Start persistent timer overlay process."""
        if not self.cfg.show_timer() or not self.cfg.is_enabled():
            return

        if self._timer_process_running():
            return

        if self.timer_overlay:
            self.timer_overlay.destroy()
            self.timer_overlay = None

        if getattr(sys, "frozen", False):
            cmd = [sys.executable, "--timer-mode"]
        else:
            cmd = [sys.executable, str(Path(__file__).parent.parent / "main.py"), "--timer-mode"]

        try:
            subprocess.Popen(
                cmd,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
            )
        except Exception as e:
            messagebox.showwarning("Таймер", f"Не удалось запустить таймер: {e}", parent=self.root)

    def _stop_timer_process(self):
        """Stop persistent timer overlay process if it is running."""
        pid = self._read_timer_pid()
        if not pid:
            return

        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/F"],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
        except Exception:
            pass

        try:
            if AGENT_PID.exists():
                AGENT_PID.unlink()
        except Exception:
            pass

    def _timer_process_running(self) -> bool:
        """Check if timer overlay process from PID file is still alive."""
        pid = self._read_timer_pid()
        if not pid:
            return False

        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            return str(pid) in result.stdout
        except Exception:
            return False

    def _read_timer_pid(self) -> Optional[int]:
        """Read timer process PID from ProgramData."""
        try:
            if not AGENT_PID.exists():
                return None
            return int(AGENT_PID.read_text(encoding="utf-8").strip())
        except Exception:
            return None
    
    def _update_status(self):
        """Update status information."""
        protected = "ВКЛЮЧЕНА" if self.cfg.is_enabled() else "ВЫКЛЮЧЕНА"
        users = self.cfg.get_controlled_users()
        users_str = f"{len(users)} пользователей" if users else "НИКТО"
        
        self.status_var.set(f"Защита: {protected} | {users_str}")
        if hasattr(self, "info_var"):
            controlled_count = len(users)
            intervals_count = len(self.cfg.get_intervals())
            break_settings = self.cfg.get_break_settings()
            break_status = (
                f"{break_settings['break_minutes']} мин. каждые "
                f"{break_settings['work_minutes']} мин."
                if break_settings["enabled"] else "Выключены"
            )
            info_text = f"""
Статус защиты: {protected}
        Контролируемых пользователей: {controlled_count if controlled_count > 0 else 'НИКТО'}
Временных интервалов: {intervals_count}
Регулярные перерывы: {break_status}
Таймер отображается: {'Да' if self.cfg.show_timer() else 'Нет'}
            """.strip()
            self.info_var.set(info_text)
    
    def run(self):
        """Start the application."""
        self.root.mainloop()
        
        # Cleanup
        if self.timer_overlay:
            try:
                self.timer_overlay.destroy()
            except tk.TclError:
                pass
            self.timer_overlay = None


def main():
    """Main entry point for settings app."""
    app = SettingsApp()
    app.run()


if __name__ == "__main__":
    main()
