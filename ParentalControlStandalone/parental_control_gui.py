"""
TimeScreen Control - GUI Parental Control Application
Single .exe, multiple modes via command-line arguments.
No console window (build with PyInstaller --windowed).
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import json
import os
import sys
import time
import hashlib
import datetime
import subprocess
import ctypes
from ctypes import wintypes
import shutil
from pathlib import Path

# ---------------------------------------------------------------------------
# Конфигурация
# ---------------------------------------------------------------------------
APP_NAME = "TimeScreen Control"
APP_VERSION = "2.0"

if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent

CONFIG_FILE = BASE_DIR / "pc_config.json"
PID_FILE    = BASE_DIR / "monitor.pid"
LOG_FILE    = BASE_DIR / "service.log"

# ---------------------------------------------------------------------------
# Утилиты
# ---------------------------------------------------------------------------

def log(msg: str) -> None:
    try:
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{stamp}] {msg}\n")
    except Exception:
        pass

def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False

def run_as_admin():
    if sys.platform == "win32" and not is_admin():
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
        sys.exit(0)

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def get_monitor_rects():
    """Возвращает список (x, y, width, height) для каждого монитора через WinAPI."""
    rects = []

    def callback(hMonitor, hdc, lprcMonitor, dwData):
        r = lprcMonitor.contents
        rects.append((r.left, r.top, r.right - r.left, r.bottom - r.top))
        return 1

    MonitorEnumProc = ctypes.WINFUNCTYPE(
        ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong,
        ctypes.POINTER(wintypes.RECT), ctypes.c_double
    )
    ctypes.windll.user32.EnumDisplayMonitors(None, None, MonitorEnumProc(callback), 0)
    return rects if rects else [(0, 0, 1920, 1080)]  # fallback

# ---------------------------------------------------------------------------
# Менеджер конфигурации
# ---------------------------------------------------------------------------

class ConfigManager:
    def __init__(self):
        self.config = self.load()

    def load(self) -> dict:
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"password_hash": None, "intervals": [], "enabled": True}

    def save(self):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)

    def set_password(self, pwd: str):
        self.config["password_hash"] = hash_password(pwd)
        self.save()

    def check_password(self, pwd: str) -> bool:
        if not self.config.get("password_hash"):
            return True
        return self.config["password_hash"] == hash_password(pwd)

    def set_intervals(self, intervals: list):
        # intervals: ["HH:MM-HH:MM", ...]
        self.config["intervals"] = intervals
        self.save()

    def set_enabled(self, state: bool):
        self.config["enabled"] = state
        self.save()

    # --- Grace-период (отсрочка блокировки после разблокировки) ---
    GRACE_MINUTES = 10

    def set_grace(self):
        """Установить grace-период на GRACE_MINUTES минут от текущего момента."""
        until = datetime.datetime.now() + datetime.timedelta(minutes=self.GRACE_MINUTES)
        self.config["grace_until"] = until.isoformat()
        self.save()

    def is_in_grace(self) -> bool:
        """Находимся ли в grace-периоде (после ручной разблокировки)."""
        ts = self.config.get("grace_until")
        if not ts:
            return False
        try:
            until = datetime.datetime.fromisoformat(ts)
            return datetime.datetime.now() < until
        except Exception:
            return False

    def clear_grace(self):
        """Сбросить grace-период."""
        self.config.pop("grace_until", None)
        self.save()

    def is_allowed_time(self) -> bool:
        if not self.config.get("enabled", True):
            return True
        intervals = self.config.get("intervals", [])
        if not intervals:
            return True

        now = datetime.datetime.now().time()
        for interval in intervals:
            try:
                start_str, end_str = interval.split("-")
                start = datetime.datetime.strptime(start_str.strip(), "%H:%M").time()
                end   = datetime.datetime.strptime(end_str.strip(), "%H:%M").time()
                if start <= end:
                    if start <= now <= end:
                        return True
                else:
                    if now >= start or now <= end:
                        return True
            except Exception:
                continue
        return False

    def get_next_event(self):
        """Return (seconds_until_event, event_type) or (None, None)."""
        intervals = self.config.get("intervals", [])
        if not intervals or not self.config.get("enabled", True):
            return None, None

        now_dt = datetime.datetime.now()
        now_t = now_dt.time()
        today = now_dt.date()

        next_lock   = None
        next_unlock = None

        for interval in intervals:
            try:
                start_str, end_str = interval.split("-")
                start = datetime.datetime.strptime(start_str.strip(), "%H:%M").time()
                end   = datetime.datetime.strptime(end_str.strip(), "%H:%M").time()

                # Сегодняшние границы
                s_dt = datetime.datetime.combine(today, start)
                e_dt = datetime.datetime.combine(today, end)

                if start > end:
                    # Интервал через полночь: разблокирован от start до полуночи И от полуночи до end
                    # Сейчас разблокировано?
                    if now_t >= start or now_t <= end:
                        # Разблокирован -> следующее событие: блокировка в end (завтра если end уже прошёл)
                        if now_t >= start:
                            # после start, блокировка завтра в end
                            candidate = e_dt + datetime.timedelta(days=1)
                        else:
                            # до end, блокировка сегодня в end (но end уже прошёл сегодня?)
                            # Если сейчас между 00:00 и end, то end сегодня ещё впереди
                            candidate = e_dt
                        if candidate > now_dt and (next_lock is None or candidate < next_lock):
                            next_lock = candidate
                    else:
                        # Заблокирован -> разблокировка в start (сегодня или завтра)
                        candidate = s_dt
                        if candidate <= now_dt:
                            candidate += datetime.timedelta(days=1)
                        if next_unlock is None or candidate < next_unlock:
                            next_unlock = candidate
                else:
                    # Обычный интервал
                    if now_t < start:
                        candidate = s_dt
                        if next_unlock is None or candidate < next_unlock:
                            next_unlock = candidate
                    elif start <= now_t < end:
                        candidate = e_dt
                        if now_dt < candidate and (next_lock is None or candidate < next_lock):
                            next_lock = candidate
                    else:
                        # after end, unlock tomorrow
                        candidate = s_dt + datetime.timedelta(days=1)
                        if next_unlock is None or candidate < next_unlock:
                            next_unlock = candidate
            except Exception:
                continue

        # Check current state
        allowed = self.is_allowed_time()
        if allowed and next_lock:
            return int((next_lock - now_dt).total_seconds()), "lock"
        elif not allowed and next_unlock:
            return int((next_unlock - now_dt).total_seconds()), "unlock"
        elif not allowed:
            return None, "blocked_no_schedule"
        return None, None


# ---------------------------------------------------------------------------
# Экран блокировки (полноэкранный)
# ---------------------------------------------------------------------------

class LockScreen:
    """Блокирует ВСЕ мониторы. Каждый монитор — отдельное полноэкранное окно."""

    def __init__(self):
        self.cfg = ConfigManager()
        self._windows = []

        monitors = get_monitor_rects()
        for i, (x, y, w, h) in enumerate(monitors):
            win = tk.Toplevel() if i > 0 else tk.Tk()
            win.title("Компьютер заблокирован")
            win.geometry(f"{w}x{h}+{x}+{y}")
            win.overrideredirect(True)
            win.attributes("-topmost", True)
            win.configure(bg="#1a1a2e")
            win.protocol("WM_DELETE_WINDOW", lambda: None)
            self._windows.append(win)

        # UI строится только на первом (главном) окне
        self.root = self._windows[0]
        self._build_ui()

        # Остальные окна — просто чёрный фон с текстом
        for win in self._windows[1:]:
            tk.Label(
                win, text="КОМПЬЮТЕР\nЗАБЛОКИРОВАН",
                font=("Arial", 36, "bold"), fg="#e94560", bg="#1a1a2e", justify="center"
            ).place(relx=0.5, rely=0.5, anchor="center")

    def _build_ui(self):
        center = tk.Frame(self.root, bg="#1a1a2e")
        center.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(
            center, text="КОМПЬЮТЕР ЗАБЛОКИРОВАН",
            font=("Arial", 30, "bold"), fg="#e94560", bg="#1a1a2e"
        ).pack(pady=(0, 15))

        tk.Label(
            center,
            text="Использование компьютера запрещено в это время.\nОбратитесь к администратору.",
            font=("Arial", 14), fg="#ffffff", bg="#1a1a2e", justify="center"
        ).pack(pady=(0, 25))

        tk.Label(center, text="Пароль администратора:", font=("Arial", 12),
                 fg="#aaaaaa", bg="#1a1a2e").pack(anchor="w", pady=(0, 5))

        self.pwd_var = tk.StringVar()
        pwd_entry = tk.Entry(center, textvariable=self.pwd_var, show="*",
                             font=("Arial", 14), width=25, justify="center")
        pwd_entry.pack(pady=(0, 10))
        pwd_entry.bind("<Return>", lambda e: self._try_unlock())
        pwd_entry.focus_set()

        self.status_lbl = tk.Label(center, text="", font=("Arial", 11),
                                   fg="#e94560", bg="#1a1a2e")
        self.status_lbl.pack(pady=(0, 15))

        tk.Button(center, text="Разблокировать", font=("Arial", 13, "bold"),
                  bg="#0f3460", fg="white", activebackground="#16213e",
                  width=20, height=2, command=self._try_unlock).pack(pady=5)

        btn_row = tk.Frame(center, bg="#1a1a2e")
        btn_row.pack(pady=15)
        tk.Button(btn_row, text="Выключить ПК", font=("Arial", 11),
                  bg="#c0392b", fg="white", width=15, height=2,
                  command=self._shutdown).pack(side="left", padx=8)
        tk.Button(btn_row, text="Перезагрузить", font=("Arial", 11),
                  bg="#e67e22", fg="white", width=15, height=2,
                  command=self._restart).pack(side="left", padx=8)

        # Часы
        self.clock_lbl = tk.Label(self.root, text="", font=("Arial", 13),
                                  fg="#ffffff", bg="#1a1a2e")
        self.clock_lbl.place(relx=0.5, rely=0.95, anchor="center")
        self._update_clock()

    def _update_clock(self):
        t = datetime.datetime.now().strftime("%H:%M:%S")
        self.clock_lbl.config(text=f"Текущее время: {t}")
        self.root.after(1000, self._update_clock)

    def _try_unlock(self):
        pwd = self.pwd_var.get()
        if self.cfg.check_password(pwd):
            self.cfg.set_grace()  # <-- 10 минут без повторной блокировки
            self._destroy_all()
        else:
            self.status_lbl.config(text="Неверный пароль!")
            self.pwd_var.set("")

    def _destroy_all(self):
        for win in self._windows:
            try:
                win.destroy()
            except Exception:
                pass

    def _shutdown(self):
        if messagebox.askyesno("Подтверждение", "Выключить компьютер?"):
            os.system("shutdown /s /t 5")

    def _restart(self):
        if messagebox.askyesno("Подтверждение", "Перезагрузить компьютер?"):
            os.system("shutdown /r /t 5")

    def run(self):
        self.root.mainloop()


# ---------------------------------------------------------------------------
# Таймер-оверлей (маленькое окно-индикатор)
# ---------------------------------------------------------------------------

class TimerOverlay:
    """Всегда поверх остальных окон. Зелёный — доступ, красный — блокировка."""

    def __init__(self):
        self.cfg = ConfigManager()
        self.root = tk.Tk()
        self.root.title("TimeScreen Timer")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg="black")
        self.root.wm_attributes("-transparentcolor", "black")

        self.lbl = tk.Label(self.root, text="", font=("Consolas", 14, "bold"),
                            bg="black", fg="#00ff00", padx=12, pady=6)
        self.lbl.pack()

        # Позиция: правый верхний угол
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        self.root.geometry(f"+{sw - 280}+10")

        self._update()
        self.root.mainloop()

    def _update(self):
        try:
            self.cfg = ConfigManager()  # Перечитываем конфиг
        except Exception:
            pass

        if self.cfg.is_in_grace():
            # В grace-периоде — показываем отсрочку
            text = "Отсрочка (grace-период)"
            self.lbl.config(fg="#ffff00")  # Жёлтый
        else:
            allowed = self.cfg.is_allowed_time()
            if allowed:
                secs, evt = self.cfg.get_next_event()
                if secs and evt == "lock":
                    h = secs // 3600
                    m = (secs % 3600) // 60
                    s = secs % 60
                    text = f"До блокировки: {h:02d}:{m:02d}:{s:02d}"
                    self.lbl.config(fg="#00ff00")
                elif evt == "unlock":
                    h = secs // 3600
                    m = (secs % 3600) // 60
                    s = secs % 60
                    text = f"Блокировка до: {h:02d}:{m:02d}:{s:02d}"
                    self.lbl.config(fg="#00ff00")
                else:
                    text = "Доступ разрешён"
                    self.lbl.config(fg="#00ff00")
            else:
                text = "КОМПЬЮТЕР ЗАБЛОКИРОВАН"
                self.lbl.config(fg="#ff0000")

        self.lbl.config(text=text)
        self.root.after(1000, self._update)


# ---------------------------------------------------------------------------
# Фоновый монитор (без окна, запускает LockScreen при необходимости)
# ---------------------------------------------------------------------------

def run_monitor():
    """Фоновый процесс: проверяет время, запускает LockScreen."""
    # Сохраняем PID для возможности остановки извне
    try:
        PID_FILE.write_text(str(os.getpid()))
    except Exception:
        pass

    log("Monitor started")
    exe = sys.executable

    # Запускаем таймер-оверлей отдельным процессом
    timer_proc = subprocess.Popen([exe, "--timer"], creationflags=0x08000000)
    log(f"Timer process started (PID {timer_proc.pid})")

    try:
        while True:
            cfg = ConfigManager()
            if not cfg.config.get("enabled", True):
                time.sleep(5)
                continue

            # Проверка grace-периода (10 минут после ручной разблокировки)
            if cfg.is_in_grace():
                time.sleep(5)
                continue

            if not cfg.is_allowed_time():
                log("Time blocked – launching lock screen")
                # Закрываем таймер
                timer_proc.terminate()
                try:
                    timer_proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    timer_proc.kill()
                # Показываем экран блокировки
                lock_proc = subprocess.Popen([exe, "--lock"], creationflags=0x08000000)
                lock_proc.wait()
                log("Lock screen closed – restarting timer")
                # Перезапускаем таймер
                timer_proc = subprocess.Popen([exe, "--timer"], creationflags=0x08000000)

            time.sleep(5)
    except KeyboardInterrupt:
        pass
    finally:
        timer_proc.terminate()
        try:
            PID_FILE.unlink(missing_ok=True)
        except Exception:
            pass
        log("Monitor stopped")


# ---------------------------------------------------------------------------
# Установщик (для пользователя, без прав админа)
# ---------------------------------------------------------------------------

def _stop_monitor_process():
    """Останавливает фоновый монитор (PID + taskkill)."""
    try:
        if PID_FILE.exists():
            pid = int(PID_FILE.read_text().strip())
            subprocess.run(["taskkill", "/f", "/pid", str(pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            PID_FILE.unlink(missing_ok=True)
    except Exception:
        pass
    # Убиваем все запущенные экземпляры
    subprocess.run(["taskkill", "/f", "/im", "TimeScreenControl.exe"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["taskkill", "/f", "/im", "wscript.exe"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.5)


def install_user():
    """Установка в %LOCALAPPDATA%\\TimeScreen, ярлыки, автозагрузка."""
    install_dir = Path(os.environ["LOCALAPPDATA"]) / "TimeScreen"
    install_dir.mkdir(parents=True, exist_ok=True)

    exe_path = Path(sys.executable)
    target_exe = install_dir / exe_path.name

    # Останавливаем монитор перед копированием (файл может быть занят)
    _stop_monitor_process()

    # Копируем себя
    if exe_path.resolve() != target_exe.resolve():
        try:
            shutil.copy2(str(exe_path), str(target_exe))
            log(f"Copied exe to {target_exe}")
        except PermissionError:
            # Файл занят — пробуем удалить и скопировать заново
            _stop_monitor_process()
            time.sleep(0.5)
            try:
                target_exe.unlink(missing_ok=True)
                shutil.copy2(str(exe_path), str(target_exe))
                log(f"Re-copied exe to {target_exe}")
            except Exception as e:
                log(f"Copy failed: {e}")
                messagebox.showerror(
                    "Ошибка копирования",
                    "Не удалось скопировать программу — файл занят.\n"
                    "Перезагрузите компьютер и попробуйте снова."
                )
                return
    else:
        log("Already running from install dir, skipping copy")

    # VBS для скрытого запуска монитора
    vbs = install_dir / "run_hidden.vbs"
    with open(vbs, "w") as f:
        f.write(f'CreateObject("WScript.Shell").Run """{target_exe}"" --monitor", 0, False\n')

    # Автозагрузка
    startup_dir = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    startup_dir.mkdir(parents=True, exist_ok=True)
    startup_link = startup_dir / "TimeScreen.lnk"
    _create_shortcut(
        link_path=startup_link,
        target="wscript.exe",
        args=f'"{vbs}"',
        workdir=str(install_dir),
        desc="TimeScreen Control - монитор"
    )

    # Ярлыки на рабочем столе
    desktop = Path.home() / "Desktop"

    _create_shortcut(
        link_path=desktop / "TimeScreen - Настройки.lnk",
        target=str(target_exe),
        args="",
        workdir=str(install_dir),
        desc="TimeScreen Control - настройки"
    )

    _create_shortcut(
        link_path=desktop / "TimeScreen - Защита.lnk",
        target=str(target_exe),
        args="--toggle",
        workdir=str(install_dir),
        desc="Включить / выключить защиту"
    )

    # Запуск монитора
    monitor_proc = subprocess.Popen(
        ["wscript", str(vbs)],
        creationflags=0x08000000
    )
    log(f"Monitor started via VBS (PID approximate)")

    messagebox.showinfo(
        "Установка завершена",
        f"Программа установлена в:\n{install_dir}\n\n"
        "На рабочем столе созданы ярлыки.\n"
        "Фоновый монитор запущен и добавлен в автозагрузку.\n\n"
        "Откройте «TimeScreen - Настройки» для настройки."
    )


def uninstall_user():
    """Удаление пользовательской установки."""
    if not messagebox.askyesno("Подтверждение", "Удалить TimeScreen Control полностью?"):
        return

    install_dir = Path(os.environ["LOCALAPPDATA"]) / "TimeScreen"

    # Убиваем процессы
    try:
        if PID_FILE.exists():
            pid = int(PID_FILE.read_text().strip())
            subprocess.run(["taskkill", "/f", "/pid", str(pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
    exe_name = Path(sys.executable).name
    subprocess.run(["taskkill", "/f", "/im", exe_name],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Удаляем автозагрузку
    startup_link = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "TimeScreen.lnk"
    if startup_link.exists():
        startup_link.unlink()

    # Удаляем ярлыки
    desktop = Path.home() / "Desktop"
    for name in ["TimeScreen - Настройки.lnk", "TimeScreen - Защита.lnk"]:
        p = desktop / name
        if p.exists():
            p.unlink()

    # Удаляем папку
    if install_dir.exists():
        shutil.rmtree(str(install_dir), ignore_errors=True)

    messagebox.showinfo("Удаление", "TimeScreen Control удалён.")


def _create_shortcut(link_path: Path, target: str, args: str, workdir: str, desc: str):
    """Создать .lnk ярлык через VBScript."""
    tmp_vbs = Path(os.environ["TEMP"]) / "_tsc_shortcut.vbs"
    args_escaped = args.replace('"', '""')
    target_escaped = target.replace('"', '""')
    with open(tmp_vbs, "w") as f:
        f.write(f'''
Set oWS = WScript.CreateObject("WScript.Shell")
sLinkFile = "{link_path}"
Set oLink = oWS.CreateShortcut(sLinkFile)
oLink.TargetPath = "{target_escaped}"
oLink.Arguments = "{args_escaped}"
oLink.WorkingDirectory = "{workdir}"
oLink.WindowStyle = 7
oLink.Description = "{desc}"
oLink.Save
''')
    subprocess.call(["cscript", "//nologo", str(tmp_vbs)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    tmp_vbs.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Главное окно настроек (GUI)
# ---------------------------------------------------------------------------

class MainApp:
    def __init__(self):
        self.cfg = ConfigManager()
        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} v{APP_VERSION}")
        self.root.geometry("520x620")
        self.root.resizable(True, True)
        self.root.minsize(480, 560)

        # Стиль
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TButton", padding=8, font=("Arial", 10))
        style.configure("TLabel", font=("Arial", 10))
        style.configure("TLabelframe.Label", font=("Arial", 11, "bold"))

        self._build_ui()
        self._refresh_status()

    # --- UI ---
    def _build_ui(self):
        # Header
        header = tk.Frame(self.root, bg="#2c3e50", height=70)
        header.pack(fill="x")
        tk.Label(header, text=APP_NAME, font=("Arial", 18, "bold"),
                 bg="#2c3e50", fg="white").pack(pady=6)
        tk.Label(header, text=f"v{APP_VERSION} — Родительский контроль",
                 font=("Arial", 10), bg="#2c3e50", fg="#bdc3c7").pack()

        body = tk.Frame(self.root, padx=20, pady=15)
        body.pack(fill="both", expand=True)

        # Статус
        self.status_var = tk.StringVar()
        tk.Label(body, textvariable=self.status_var, font=("Arial", 12, "bold"),
                 fg="#2c3e50").pack(anchor="w", pady=(0, 10))

        # --- Безопасность ---
        sec_frame = ttk.LabelFrame(body, text="Безопасность", padding=12)
        sec_frame.pack(fill="x", pady=6)

        ttk.Label(sec_frame, text="Пароль администратора:").pack(anchor="w")
        self.pass_entry = ttk.Entry(sec_frame, show="*", font=("Arial", 12))
        self.pass_entry.pack(fill="x", pady=(5, 8))
        ttk.Button(sec_frame, text="Установить / Изменить пароль",
                   command=self._set_password).pack(fill="x")

        # --- Расписание ---
        sched_frame = ttk.LabelFrame(body, text="Расписание доступа", padding=12)
        sched_frame.pack(fill="x", pady=6)

        ttk.Label(sched_frame, text="Интервалы (формат: ЧЧ:ММ-ЧЧ:ММ, через запятую):").pack(anchor="w")
        ttk.Label(sched_frame, text="Пример: 08:00-22:00, 14:00-16:00",
                  font=("Arial", 9), foreground="gray").pack(anchor="w")

        self.sched_entry = ttk.Entry(sched_frame, font=("Arial", 12))
        self.sched_entry.pack(fill="x", pady=(5, 8))
        ttk.Button(sched_frame, text="Сохранить расписание",
                   command=self._save_schedule).pack(fill="x")

        # --- Управление ---
        ctrl_frame = ttk.LabelFrame(body, text="Управление защитой", padding=12)
        ctrl_frame.pack(fill="x", pady=6)

        self.btn_start = tk.Button(ctrl_frame, text="Запустить защиту",
                                   font=("Arial", 11, "bold"), bg="#27ae60",
                                   fg="white", relief="flat", padx=10, pady=8,
                                   command=self._start_protection)
        self.btn_start.pack(fill="x", pady=3)

        self.btn_stop = tk.Button(ctrl_frame, text="Остановить защиту",
                                  font=("Arial", 11, "bold"), bg="#c0392b",
                                  fg="white", relief="flat", padx=10, pady=8,
                                  state="disabled", command=self._stop_protection)
        self.btn_stop.pack(fill="x", pady=3)

        self.btn_toggle = tk.Button(ctrl_frame, text="Включить / Выключить защиту",
                                    font=("Arial", 10), relief="flat", padx=10, pady=6,
                                    command=self._toggle)
        self.btn_toggle.pack(fill="x", pady=3)

        # --- Сервис ---
        svc_frame = ttk.LabelFrame(body, text="Установка на компьютер", padding=12)
        svc_frame.pack(fill="x", pady=6)

        tk.Button(svc_frame, text="Установить (для текущего пользователя)",
                  font=("Arial", 10), bg="#2980b9", fg="white",
                  relief="flat", padx=10, pady=6,
                  command=self._install).pack(fill="x", pady=2)

        tk.Button(svc_frame, text="Удалить программу",
                  font=("Arial", 10), bg="#7f8c8d", fg="white",
                  relief="flat", padx=10, pady=6,
                  command=self._uninstall).pack(fill="x", pady=2)

        # Подсказка
        tk.Label(body, text="Программа не требует прав администратора.\n"
                 "Для полной защиты рекомендуется установить через кнопку выше.",
                 font=("Arial", 9), fg="#7f8c8d", justify="center",
                 wraplength=440).pack(pady=(10, 0))

    # --- Действия ---
    def _refresh_status(self):
        has_pwd = bool(self.cfg.config.get("password_hash"))
        intervals = self.cfg.config.get("intervals", [])
        enabled = self.cfg.config.get("enabled", True)

        if not has_pwd:
            self.status_var.set("Статус: [НЕ НАСТРОЕНО] Установите пароль")
        elif not intervals:
            self.status_var.set("Статус: [Пароль задан] Добавьте расписание")
        elif enabled:
            self.status_var.set("Статус: [АКТИВНА] Защита включена")
        else:
            self.status_var.set("Статус: [ОТКЛЮЧЕНА] Защита выключена")

        self.sched_entry.delete(0, "end")
        if intervals:
            self.sched_entry.insert(0, ", ".join(intervals))

        # Проверка, запущен ли монитор
        running = self._is_monitor_running()
        if running:
            self.btn_start.config(state="disabled")
            self.btn_stop.config(state="normal")
        else:
            self.btn_start.config(state="normal")
            self.btn_stop.config(state="disabled")

    def _is_monitor_running(self) -> bool:
        """Проверяем, запущен ли монитор (по PID-файлу)."""
        if not PID_FILE.exists():
            return False
        try:
            pid = int(PID_FILE.read_text().strip())
            # Проверяем, существует ли процесс с таким PID
            result = subprocess.run(
                ["tasklist", "/fi", f"PID eq {pid}", "/fo", "csv", "/nh"],
                capture_output=True, text=True
            )
            return str(pid) in result.stdout
        except Exception:
            return False

    def _set_password(self):
        # Если пароль уже установлен — требуем старый
        if self.cfg.config.get("password_hash"):
            old = simpledialog.askstring("Подтверждение", "Введите СТАРЫЙ пароль:", show="*")
            if not old or not self.cfg.check_password(old):
                if old:
                    messagebox.showerror("Ошибка", "Неверный старый пароль!")
                return

        pwd = self.pass_entry.get().strip()
        if len(pwd) < 4:
            messagebox.showerror("Ошибка", "Пароль должен содержать минимум 4 символа.")
            return
        self.cfg.set_password(pwd)
        self.pass_entry.delete(0, "end")
        messagebox.showinfo("Готово", "Пароль успешно установлен!")
        self._refresh_status()

    def _save_schedule(self):
        # Если пароль установлен — требуем подтверждение
        if self.cfg.config.get("password_hash"):
            pwd = simpledialog.askstring("Подтверждение", "Введите пароль для изменения расписания:", show="*")
            if not pwd or not self.cfg.check_password(pwd):
                if pwd:
                    messagebox.showerror("Ошибка", "Неверный пароль!")
                return

        raw = self.sched_entry.get().strip()
        if not raw:
            self.cfg.set_intervals([])
            messagebox.showinfo("Готово", "Расписание очищено.")
            self._refresh_status()
            return

        intervals = [x.strip() for x in raw.split(",") if x.strip()]
        for iv in intervals:
            if "-" not in iv or len(iv.split("-")) != 2:
                messagebox.showerror("Ошибка", f"Неверный формат: {iv}\nИспользуйте: ЧЧ:ММ-ЧЧ:ММ")
                return
            parts = iv.split("-")
            for p in parts:
                try:
                    datetime.datetime.strptime(p.strip(), "%H:%M")
                except ValueError:
                    messagebox.showerror("Ошибка", f"Неверное время: {p}")
                    return

        self.cfg.set_intervals(intervals)
        messagebox.showinfo("Готово", f"Сохранено интервалов: {len(intervals)}")
        self._refresh_status()

    def _start_protection(self):
        if not self.cfg.config.get("password_hash"):
            messagebox.showwarning("Внимание", "Сначала установите пароль!")
            return
        if not self.cfg.config.get("intervals"):
            messagebox.showwarning("Внимание", "Сначала задайте расписание!")
            return

        self.cfg.set_enabled(True)
        exe = sys.executable
        subprocess.Popen([exe, "--monitor"], creationflags=0x08000000)
        log("Monitor started from GUI")
        messagebox.showinfo("Запущено", "Мониторинг времени активирован.\nВ углу экрана появится индикатор.")
        self._refresh_status()

    def _stop_protection(self):
        pwd = simpledialog.askstring("Подтверждение", "Введите пароль для остановки:", show="*")
        if pwd and self.cfg.check_password(pwd):
            self.cfg.set_enabled(False)
            # Убиваем монитор по PID
            self._kill_monitor()
            messagebox.showinfo("Стоп", "Защита остановлена.")
            self._refresh_status()
        elif pwd:
            messagebox.showerror("Ошибка", "Неверный пароль!")

    def _toggle(self):
        if self.cfg.config.get("password_hash"):
            pwd = simpledialog.askstring("Подтверждение", "Введите пароль для вкл/выкл защиты:", show="*")
            if not pwd or not self.cfg.check_password(pwd):
                if pwd:
                    messagebox.showerror("Ошибка", "Неверный пароль!")
                return

        new_state = not self.cfg.config.get("enabled", True)
        self.cfg.set_enabled(new_state)
        state_text = "ВКЛЮЧЕНА" if new_state else "ВЫКЛЮЧЕНА"
        messagebox.showinfo("Защита", f"Защита {state_text}.")
        self._refresh_status()

    def _kill_monitor(self):
        """Останавливает фоновый монитор по PID."""
        try:
            if PID_FILE.exists():
                pid = int(PID_FILE.read_text().strip())
                subprocess.run(["taskkill", "/f", "/pid", str(pid)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                PID_FILE.unlink(missing_ok=True)
        except Exception:
            pass
        # Дополнительно: убиваем все процессы, запущенные из того же exe (на случай если PID не помог)
        exe_name = Path(sys.executable).name
        subprocess.run(["taskkill", "/f", "/im", exe_name],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _install(self):
        install_user()
        self._refresh_status()

    def _uninstall(self):
        uninstall_user()
        self._refresh_status()

    def run(self):
        self.root.mainloop()


# ---------------------------------------------------------------------------
# Точка входа
# ---------------------------------------------------------------------------

def main():
    args = sys.argv[1:]

    if not args:
        # Запуск без аргументов = главное окно
        app = MainApp()
        app.run()
    elif args[0] == "--lock":
        LockScreen().run()
    elif args[0] == "--timer":
        TimerOverlay()
    elif args[0] == "--monitor":
        run_monitor()
    elif args[0] == "--toggle":
        cfg = ConfigManager()
        if cfg.config.get("password_hash"):
            # Запрашиваем пароль через simpledialog
            root = tk.Tk()
            root.withdraw()
            pwd = simpledialog.askstring("Подтверждение", "Введите пароль для вкл/выкл защиты:", show="*")
            root.destroy()
            if not pwd or not cfg.check_password(pwd):
                if pwd:
                    # Показываем ошибку через messagebox
                    root2 = tk.Tk()
                    root2.withdraw()
                    messagebox.showerror("Ошибка", "Неверный пароль!")
                    root2.destroy()
                return
        cfg.set_enabled(not cfg.config.get("enabled", True))
        # Показываем результат
        root3 = tk.Tk()
        root3.withdraw()
        state_text = "ВКЛЮЧЕНА" if cfg.config["enabled"] else "ВЫКЛЮЧЕНА"
        messagebox.showinfo("Защита", f"Защита {state_text}.")
        root3.destroy()
    elif args[0] == "install-user":
        install_user()
    elif args[0] == "uninstall-user":
        uninstall_user()
    elif args[0] == "--help" or args[0] == "help":
        print(f"{APP_NAME} v{APP_VERSION}")
        print("  (без аргументов)    – главное окно настроек")
        print("  --monitor           – фоновый мониторинг времени")
        print("  --timer             – таймер-индикатор поверх окон")
        print("  --toggle            – быстрое вкл/выкл защиты")
        print("  install-user        – установить для пользователя")
        print("  uninstall-user      – удалить программу")
    else:
        print(f"Неизвестная команда: {args[0]}")
        print("Используйте --help для справки")


if __name__ == "__main__":
    main()
