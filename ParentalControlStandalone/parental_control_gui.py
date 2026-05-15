"""
TimeScreen Control - GUI Parental Control Application
Service-based architecture:
  - Windows service (SYSTEM) = time monitor (headless, unkillable)
  - User agent (autostart) = timer overlay + lock screen (GUI in user session)
  - Communication via flag file: %PROGRAMDATA%\\TimeScreen\\lock_flag
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
APP_VERSION = "2.3"
_CREATE_NO_WINDOW = 0x08000000  # Подавляет мелькание консольных окон subprocess

if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent

CONFIG_FILE   = Path(os.environ.get("PROGRAMDATA", "C:\\ProgramData")) / "TimeScreen" / "pc_config.json"
LOCK_FLAG     = Path(os.environ.get("PROGRAMDATA", "C:\\ProgramData")) / "TimeScreen" / "lock_flag"
PID_FILE      = Path(os.environ.get("PROGRAMDATA", "C:\\ProgramData")) / "TimeScreen" / "monitor.pid"
AGENT_PID     = Path(os.environ.get("PROGRAMDATA", "C:\\ProgramData")) / "TimeScreen" / "agent.pid"
LOG_FILE      = Path(os.environ.get("PROGRAMDATA", "C:\\ProgramData")) / "TimeScreen" / "service.log"
SERVICE_NAME  = "TimeScreenControl"
INSTALL_DIR   = Path(os.environ["LOCALAPPDATA"]) / "TimeScreen"

# ---------------------------------------------------------------------------
# Утилиты
# ---------------------------------------------------------------------------

def log(msg: str) -> None:
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
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

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def get_monitor_rects():
    """Возвращает список (x, y, width, height) для каждого монитора."""
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
    return rects if rects else [(0, 0, 1920, 1080)]

# ---------------------------------------------------------------------------
# Менеджер конфигурации
# ---------------------------------------------------------------------------

class ConfigManager:
    def __init__(self):
        self.config = self.load()

    def load(self) -> dict:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8-sig") as f:
                    raw = json.load(f)
                stored_hash = raw.pop("_hash", None)
                if stored_hash:
                    expected = self._compute_hash(raw)
                    if stored_hash != expected:
                        log("CONFIG TAMPERED – entering lockdown")
                        return {"password_hash": None, "intervals": [],
                                "enabled": True, "show_timer": False,
                                "controlled_users": [], "_tampered": True}
                return raw
            except Exception:
                pass
        return {"password_hash": None, "intervals": [], "enabled": True,
                "show_timer": True, "controlled_users": []}

    def _compute_hash(self, data: dict) -> str:
        clean = {k: v for k, v in data.items() if k != "_hash"}
        payload = json.dumps(clean, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def save(self):
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = self.config.copy()
        data.pop("_tampered", None)
        data["_hash"] = self._compute_hash(data)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def set_password(self, pwd: str):
        self.config["password_hash"] = hash_password(pwd)
        self.save()

    def check_password(self, pwd: str) -> bool:
        if self.config.get("_tampered"):
            return False
        if not self.config.get("password_hash"):
            return True
        return self.config["password_hash"] == hash_password(pwd)

    def set_intervals(self, intervals: list):
        self.config["intervals"] = intervals
        self.save()

    def set_enabled(self, state: bool):
        self.config["enabled"] = state
        self.save()

    def set_controlled_users(self, users: list):
        self.config["controlled_users"] = users
        self.save()

    def is_controlled_user(self) -> bool:
        controlled = self.config.get("controlled_users", [])
        if not controlled:
            return True  # Пустой список = контролировать всех
        current = os.environ.get("USERNAME", "")
        return current.lower() in [u.lower() for u in controlled]

    GRACE_MINUTES = 10

    def set_grace(self):
        until = datetime.datetime.now() + datetime.timedelta(minutes=self.GRACE_MINUTES)
        self.config["grace_until"] = until.isoformat()
        self.save()

    def is_in_grace(self) -> bool:
        ts = self.config.get("grace_until")
        if not ts:
            return False
        try:
            until = datetime.datetime.fromisoformat(ts)
            return datetime.datetime.now() < until
        except Exception:
            return False

    def clear_grace(self):
        self.config.pop("grace_until", None)
        self.save()

    def is_allowed_time(self) -> bool:
        if self.config.get("_tampered"):
            return False
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
        intervals = self.config.get("intervals", [])
        if not intervals or not self.config.get("enabled", True):
            return None, None
        now_dt = datetime.datetime.now()
        now_t = now_dt.time()
        today = now_dt.date()
        next_lock = None; next_unlock = None
        for interval in intervals:
            try:
                start_str, end_str = interval.split("-")
                start = datetime.datetime.strptime(start_str.strip(), "%H:%M").time()
                end   = datetime.datetime.strptime(end_str.strip(), "%H:%M").time()
                s_dt = datetime.datetime.combine(today, start)
                e_dt = datetime.datetime.combine(today, end)
                if start > end:
                    if now_t >= start or now_t <= end:
                        if now_t >= start:
                            candidate = e_dt + datetime.timedelta(days=1)
                        else:
                            candidate = e_dt
                        if candidate > now_dt and (next_lock is None or candidate < next_lock):
                            next_lock = candidate
                    else:
                        candidate = s_dt
                        if candidate <= now_dt:
                            candidate += datetime.timedelta(days=1)
                        if next_unlock is None or candidate < next_unlock:
                            next_unlock = candidate
                else:
                    if now_t < start:
                        candidate = s_dt
                        if next_unlock is None or candidate < next_unlock:
                            next_unlock = candidate
                    elif start <= now_t < end:
                        candidate = e_dt
                        if now_dt < candidate and (next_lock is None or candidate < next_lock):
                            next_lock = candidate
                    else:
                        candidate = s_dt + datetime.timedelta(days=1)
                        if next_unlock is None or candidate < next_unlock:
                            next_unlock = candidate
            except Exception:
                continue
        allowed = self.is_allowed_time()
        if allowed and next_lock:
            return int((next_lock - now_dt).total_seconds()), "lock"
        elif not allowed and next_unlock:
            return int((next_unlock - now_dt).total_seconds()), "unlock"
        elif not allowed:
            return None, "blocked_no_schedule"
        return None, None


# ---------------------------------------------------------------------------
# Экран блокировки
# ---------------------------------------------------------------------------

class LockScreen:
    def __init__(self):
        try:
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
            self.root = self._windows[0]
            self._build_ui()
            for win in self._windows[1:]:
                tk.Label(win, text="КОМПЬЮТЕР\nЗАБЛОКИРОВАН",
                         font=("Arial", 36, "bold"), fg="#e94560", bg="#1a1a2e",
                         justify="center").place(relx=0.5, rely=0.5, anchor="center")
        except Exception as e:
            log(f"LockScreen init error: {e}")
            raise

    def _build_ui(self):
        center = tk.Frame(self.root, bg="#1a1a2e")
        center.place(relx=0.5, rely=0.5, anchor="center")
        tk.Label(center, text="КОМПЬЮТЕР ЗАБЛОКИРОВАН",
                 font=("Arial", 30, "bold"), fg="#e94560", bg="#1a1a2e").pack(pady=(0, 15))
        tk.Label(center, text="Использование компьютера запрещено в это время.\nОбратитесь к администратору.",
                 font=("Arial", 14), fg="#ffffff", bg="#1a1a2e", justify="center").pack(pady=(0, 25))
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
        tk.Button(center, text="Войти как администратор Windows",
                  font=("Arial", 10), bg="#8e44ad", fg="white",
                  relief="flat", padx=10, pady=4,
                  command=self._admin_unlock).pack(pady=(10, 0))
        self.clock_lbl = tk.Label(self.root, text="", font=("Arial", 13),
                                  fg="#ffffff", bg="#1a1a2e")
        self.clock_lbl.place(relx=0.5, rely=0.95, anchor="center")
        self._update_clock()
        self._check_auto_unlock()  # Запускаем периодическую проверку авторазблокировки

    def _update_clock(self):
        t = datetime.datetime.now().strftime("%H:%M:%S")
        self.clock_lbl.config(text=f"Текущее время: {t}")
        self.root.after(1000, self._update_clock)

    def _check_auto_unlock(self):
        """Периодически проверяет: не настал ли разрешённый период.
        Если LOCK_FLAG исчез (служба удалила) или время стало разрешённым —
        автоматически закрыть экран блокировки с grace-периодом."""
        try:
            cfg = ConfigManager()
            if not LOCK_FLAG.exists() or cfg.is_allowed_time():
                log("Auto-unlock: lock flag removed or time is now allowed")
                cfg.set_grace()
                LOCK_FLAG.unlink(missing_ok=True)
                self._destroy_all()
                return
        except Exception:
            pass
        # Продолжаем проверять каждые 3 секунды
        self.root.after(3000, self._check_auto_unlock)

    def _try_unlock(self):
        pwd = self.pwd_var.get()
        if self.cfg.check_password(pwd):
            self.cfg.set_grace()
            # Удаляем флаг блокировки
            LOCK_FLAG.unlink(missing_ok=True)
            self._destroy_all()
        else:
            self.status_lbl.config(text="Неверный пароль!")
            self.pwd_var.set("")

    def _admin_unlock(self):
        if is_admin():
            cfg = ConfigManager()
            if cfg.config.get("_tampered"):
                CONFIG_FILE.unlink(missing_ok=True)
                subprocess.run(["taskkill", "/f", "/im", "TimeScreenControl.exe"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.Popen([sys.executable], creationflags=0x08000000)
                self._destroy_all()
            else:
                self.cfg.set_grace()
                LOCK_FLAG.unlink(missing_ok=True)
                self._destroy_all()
        else:
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, "--recovery", None, 1
            )

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
# Таймер-оверлей
# ---------------------------------------------------------------------------

class TimerOverlay:
    def __init__(self):
        try:
            self.cfg = ConfigManager()
            self.root = tk.Tk()
            self.root.title("TimeScreen Timer")
            self.root.overrideredirect(True)
            self.root.attributes("-topmost", True)
            self.root.attributes("-alpha", 0.92)  # Полупрозрачность вместо transparentcolor (не мерцает)
            self.root.configure(bg="#0a0a0a")
            self.root.attributes("-toolwindow", True)  # Не показывать в панели задач
            self.lbl = tk.Label(self.root, text="", font=("Consolas", 14, "bold"),
                                bg="#0a0a0a", fg="#00ff00", padx=12, pady=6)
            self.lbl.pack()
            self.root.update_idletasks()
            sw = self.root.winfo_screenwidth()
            self.root.geometry(f"+{sw - 280}+10")
            self._tick = 0
            self._update()
            self.root.mainloop()
        except Exception as e:
            log(f"TimerOverlay crashed: {e}")
            # Попытка показать ошибку через messagebox
            try:
                import traceback
                log(traceback.format_exc())
            except Exception:
                pass

    def _update(self):
        self._tick += 1
        # Watchdog: проверяем PID службы
        if self._tick % 10 == 0:
            self._watchdog()
        try:
            self.cfg = ConfigManager()
        except Exception:
            pass

        if self.cfg.is_in_grace():
            text = "Отсрочка (grace-период)"
            self.lbl.config(fg="#ffff00")
        elif self.cfg.config.get("_tampered"):
            text = "КОНФИГ ПОВРЕЖДЁН!"
            self.lbl.config(fg="#ff0000")
        else:
            allowed = self.cfg.is_allowed_time()
            if allowed:
                secs, evt = self.cfg.get_next_event()
                if evt is None and not self.cfg.config.get("intervals"):
                    text = "Расписание не задано"
                    self.lbl.config(fg="#888888")
                elif secs and evt == "lock":
                    h = secs // 3600; m = (secs % 3600) // 60; s = secs % 60
                    text = f"До блокировки: {h:02d}:{m:02d}:{s:02d}"
                    self.lbl.config(fg="#00ff00")
                elif evt == "unlock":
                    h = secs // 3600; m = (secs % 3600) // 60; s = secs % 60
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

    def _watchdog(self):
        try:
            if not PID_FILE.exists():
                return
            pid = int(PID_FILE.read_text().strip())
            result = subprocess.run(
                ["tasklist", "/fi", f"PID eq {pid}", "/fo", "csv", "/nh"],
                capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            if str(pid) not in result.stdout:
                log("Timer: monitor dead – restarting service")
                subprocess.run(["sc", "start", SERVICE_NAME],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               creationflags=subprocess.CREATE_NO_WINDOW)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Служебный монитор (только проверка времени, без GUI)
# ---------------------------------------------------------------------------

def run_monitor():
    """Фоновый монитор (запускается либо службой, либо вручную)."""
    try:
        PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text(str(os.getpid()))
    except Exception:
        pass
    log("Monitor started")
    loop_count = 0
    try:
        while True:
            loop_count += 1
            cfg = ConfigManager()
            if not cfg.config.get("enabled", True):
                time.sleep(5)
                continue

            # Вотчдог: проверяем жив ли агент (каждые 30 сек = 6 циклов)
            if loop_count % 6 == 0:
                _check_and_restart_agent()

            if cfg.is_in_grace():
                time.sleep(5)
                continue
            if not cfg.is_controlled_user():
                time.sleep(5)
                continue
            if not cfg.is_allowed_time():
                try:
                    LOCK_FLAG.parent.mkdir(parents=True, exist_ok=True)
                    LOCK_FLAG.write_text("1")
                except Exception:
                    pass
            else:
                LOCK_FLAG.unlink(missing_ok=True)
            time.sleep(5)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            PID_FILE.unlink(missing_ok=True)
        except Exception:
            pass
        LOCK_FLAG.unlink(missing_ok=True)
        log("Monitor stopped")


def _check_and_restart_agent():
    """Если агент убит — перезапустить через schtasks в сессии пользователя."""
    if not AGENT_PID.exists():
        return
    try:
        pid = int(AGENT_PID.read_text().strip())
        result = subprocess.run(
            ["tasklist", "/fi", f"PID eq {pid}", "/fo", "csv", "/nh"],
            capture_output=True, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        if str(pid) not in result.stdout:
            log("Agent dead – restarting via schtasks")
            agent_vbs = INSTALL_DIR / "run_agent.vbs"
            if agent_vbs.exists():
                sp_kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
                             "creationflags": subprocess.CREATE_NO_WINDOW}
                subprocess.run(
                    ["schtasks", "/create", "/tn", "TimeScreenAgentRestart",
                     "/tr", f'wscript.exe "{agent_vbs}"',
                     "/sc", "once", "/st", "00:00", "/it", "/f"], **sp_kwargs
                )
                subprocess.run(
                    ["schtasks", "/run", "/tn", "TimeScreenAgentRestart"], **sp_kwargs
                )
                subprocess.run(
                    ["schtasks", "/delete", "/tn", "TimeScreenAgentRestart", "/f"], **sp_kwargs
                )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Пользовательский агент (таймер + блокировка по флагу)
# ---------------------------------------------------------------------------

def run_user_agent():
    """Агент в сессии пользователя: таймер + проверка флага блокировки."""
    exe = sys.executable
    cfg = ConfigManager()

    # Пишем свой PID для вотчдога службы
    try:
        AGENT_PID.parent.mkdir(parents=True, exist_ok=True)
        AGENT_PID.write_text(str(os.getpid()))
    except Exception:
        pass

    # Запускаем таймер если нужно
    timer_proc = None
    if cfg.config.get("show_timer", True):
        try:
            timer_proc = subprocess.Popen([exe, "--timer"], creationflags=0x08000000)
        except Exception as e:
            log(f"Failed to start timer: {e}")

    log("User agent started")
    try:
        while True:
            cfg = ConfigManager()

            # Проверяем флаг блокировки
            if LOCK_FLAG.exists() and cfg.is_controlled_user():
                log("Lock flag detected – launching lock screen")
                if timer_proc is not None:
                    timer_proc.terminate()
                    try:
                        timer_proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        timer_proc.kill()
                    timer_proc = None
                lock_proc = subprocess.Popen([exe, "--lock"], creationflags=0x08000000)
                lock_proc.wait()
                log("Lock screen closed")
                if cfg.config.get("show_timer", True):
                    try:
                        timer_proc = subprocess.Popen([exe, "--timer"], creationflags=0x08000000)
                    except Exception as e:
                        log(f"Failed to restart timer: {e}")

            time.sleep(3)
    except KeyboardInterrupt:
        pass
    finally:
        if timer_proc is not None:
            timer_proc.terminate()
        try:
            AGENT_PID.unlink(missing_ok=True)
        except Exception:
            pass
        log("User agent stopped")


# ---------------------------------------------------------------------------
# Служба Windows
# ---------------------------------------------------------------------------

def _install_windows_service():
    """Установка Windows-службы (требует прав администратора)."""
    if not is_admin():
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, "--install-service", None, 1
        )
        return

    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    exe_path = Path(sys.executable)
    target_gui = INSTALL_DIR / exe_path.name  # TimeScreenControl.exe

    # Копируем GUI exe
    if exe_path.resolve() != target_gui.resolve():
        try:
            shutil.copy2(str(exe_path), str(target_gui))
        except Exception:
            pass

    # Ищем и копируем service daemon (директория --onedir сборки)
    daemon_dir_candidates = [
        exe_path.parent / "TimeScreenService",
        Path(os.environ.get("TEMP", ".")) / "tsc_installer" / "TimeScreenService",
    ]
    target_daemon_dir = INSTALL_DIR / "TimeScreenService"
    target_daemon_exe = target_daemon_dir / "TimeScreenService.exe"
    daemon_found = False
    for src_dir in daemon_dir_candidates:
        src_exe = src_dir / "TimeScreenService.exe"
        if src_dir.is_dir() and src_exe.exists() and src_dir.resolve() != target_daemon_dir.resolve():
            try:
                if target_daemon_dir.exists():
                    shutil.rmtree(str(target_daemon_dir), ignore_errors=True)
                shutil.copytree(str(src_dir), str(target_daemon_dir))
                daemon_found = True
                break
            except Exception:
                continue

    if not daemon_found and target_daemon_exe.exists():
        daemon_found = True  # уже на месте

    if not daemon_found:
        messagebox.showwarning(
            "Внимание",
            "Не найден каталог службы TimeScreenService\\TimeScreenService.exe.\n"
            "Он должен лежать рядом с TimeScreenControl.exe.\n"
            "Пересоберите проект с --onedir."
        )
        return

    try:
        subprocess.run(["sc", "stop", SERVICE_NAME],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2)
        subprocess.run(["sc", "delete", SERVICE_NAME],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)
        result = subprocess.run(
            ["sc", "create", SERVICE_NAME,
             "binPath=", f'"{target_daemon_exe}"',
             "DisplayName=", "TimeScreen - Родительский контроль",
             "start=", "auto"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            subprocess.run(["sc", "start", SERVICE_NAME],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            messagebox.showinfo("Готово", "Служба установлена и запущена.")
        else:
            messagebox.showerror("Ошибка", f"Не удалось создать службу:\n{result.stderr}")
    except Exception as e:
        messagebox.showerror("Ошибка", str(e))


def _uninstall_windows_service():
    if not is_admin():
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, "--uninstall-service", None, 1
        )
        return
    _delete_service_internal()


def _delete_service_internal():
    """Удаление службы (без проверки прав — вызывающий уже админ)."""
    try:
        for _ in range(3):
            subprocess.run(["sc", "stop", SERVICE_NAME],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(2)
        result = subprocess.run(["sc", "delete", SERVICE_NAME],
                                capture_output=True, text=True)
        if "1072" in result.stderr or "1072" in result.stdout:
            # Служба помечена на удаление — нужна перезагрузка
            if messagebox.askyesno(
                "Требуется перезагрузка",
                "Служба помечена на удаление и исчезнет после перезагрузки.\n\n"
                "Перезагрузить компьютер сейчас?"
            ):
                os.system("shutdown /r /t 10")
            else:
                messagebox.showinfo("Информация",
                                    "Служба будет удалена при следующей перезагрузке.")
        else:
            messagebox.showinfo("Готово", "Служба удалена.")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Установщик пользователя
# ---------------------------------------------------------------------------

def _check_service_static():
    """Проверка состояния службы (статическая, не метод класса)."""
    try:
        result = subprocess.run(
            ["sc", "query", SERVICE_NAME],
            capture_output=True, text=True,
            creationflags=_CREATE_NO_WINDOW
        )
        installed = "FAILED" not in result.stdout and "1060" not in result.stdout
        running = "RUNNING" in result.stdout
        return installed, running
    except Exception:
        return False, False


def _stop_monitor_process():
    my_pid = os.getpid()
    my_name = Path(sys.executable).name
    for pid_path in (PID_FILE, INSTALL_DIR / "monitor.pid"):
        try:
            if pid_path.exists():
                pid = int(pid_path.read_text().strip())
                if pid != my_pid:
                    subprocess.run(["taskkill", "/f", "/pid", str(pid)],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                pid_path.unlink(missing_ok=True)
        except Exception:
            pass
    subprocess.run(["taskkill", "/f", "/im", my_name, "/fi", f"PID ne {my_pid}"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["taskkill", "/f", "/im", "wscript.exe"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.8)


def _run_cleanup_bat(directory: Path):
    my_pid = os.getpid()
    tmp_bat = Path(os.environ["TEMP"]) / "_tsc_cleanup.bat"
    with open(tmp_bat, "w") as f:
        f.write(f'''@echo off
:wait
tasklist /fi "PID eq {my_pid}" 2>nul | find "{my_pid}" >nul
if not errorlevel 1 (timeout /t 1 >nul & goto wait)
sc stop {SERVICE_NAME} 2>nul
sc delete {SERVICE_NAME} 2>nul
rmdir /s /q "{directory}" 2>nul
del "%~f0" 2>nul
''')
    subprocess.Popen(["cmd", "/c", str(tmp_bat)], creationflags=0x08000000)


def _create_shortcut(link_path: Path, target: str, args: str, workdir: str, desc: str, icon: str = ""):
    tmp_vbs = Path(os.environ["TEMP"]) / "_tsc_shortcut.vbs"
    args_escaped = args.replace('"', '""')
    target_escaped = target.replace('"', '""')
    icon_line = f'oLink.IconLocation = "{icon}"\n' if icon else ""
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
{icon_line}oLink.Save
''')
    subprocess.call(["cscript", "//nologo", str(tmp_vbs)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    tmp_vbs.unlink(missing_ok=True)


def install_user():
    """Установка для текущего пользователя: ярлыки, автозагрузка агента."""
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    exe_path = Path(sys.executable)
    target_exe = INSTALL_DIR / exe_path.name

    _stop_monitor_process()

    # Копируем себя (GUI)
    if exe_path.resolve() != target_exe.resolve():
        try:
            shutil.copy2(str(exe_path), str(target_exe))
        except PermissionError:
            _stop_monitor_process()
            time.sleep(0.5)
            try:
                target_exe.unlink(missing_ok=True)
                shutil.copy2(str(exe_path), str(target_exe))
            except Exception:
                pass

    # Копируем Service Daemon (директория --onedir сборки)
    daemon_dir_src = exe_path.parent / "TimeScreenService"
    daemon_dir_dst = INSTALL_DIR / "TimeScreenService"
    if daemon_dir_src.is_dir() and daemon_dir_src.resolve() != daemon_dir_dst.resolve():
        try:
            if daemon_dir_dst.exists():
                shutil.rmtree(str(daemon_dir_dst), ignore_errors=True)
            shutil.copytree(str(daemon_dir_src), str(daemon_dir_dst))
        except Exception:
            pass

    # VBS для скрытого запуска пользовательского агента (локально + в ProgramData для службы)
    vbs_local = INSTALL_DIR / "run_agent.vbs"
    vbs_content = f'CreateObject("WScript.Shell").Run """{target_exe}"" --user-agent", 0, False\n'
    with open(vbs_local, "w") as f:
        f.write(vbs_content)
    # Дублируем в ProgramData — служба (SYSTEM) читает оттуда
    vbs_pdata = CONFIG_FILE.parent / "run_agent.vbs"
    try:
        vbs_pdata.parent.mkdir(parents=True, exist_ok=True)
        with open(vbs_pdata, "w") as f:
            f.write(vbs_content)
    except OSError:
        pass  # нет прав на ProgramData — служба сама создаст при необходимости

    # Автозагрузка
    startup_dir = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    startup_dir.mkdir(parents=True, exist_ok=True)
    _create_shortcut(
        link_path=startup_dir / "TimeScreen.lnk",
        target="wscript.exe",
        args=f'"{vbs_local}"',
        workdir=str(INSTALL_DIR),
        desc="TimeScreen Control - агент",
        icon=f"{target_exe},0"
    )

    # Ярлыки на рабочем столе
    desktop = Path.home() / "Desktop"
    _create_shortcut(
        link_path=desktop / "TimeScreen - Настройки.lnk",
        target=str(target_exe), args="", workdir=str(INSTALL_DIR),
        desc="TimeScreen Control - настройки",
        icon=f"{target_exe},0"
    )
    _create_shortcut(
        link_path=desktop / "TimeScreen - Защита.lnk",
        target=str(target_exe), args="--toggle", workdir=str(INSTALL_DIR),
        desc="Включить / выключить защиту",
        icon=f"{target_exe},0"
    )

    messagebox.showinfo(
        "Установка завершена",
        f"Программа установлена в:\n{INSTALL_DIR}\n\n"
        "Ярлыки созданы на рабочем столе.\n"
        "Агент добавлен в автозагрузку.\n\n"
        "ДАЛЕЕ:\n"
        "1. Откройте «TimeScreen - Настройки»\n"
        "2. Задайте пароль и расписание\n"
        "3. Нажмите «Запустить защиту»\n\n"
        "Для максимальной защиты:\n"
        "вкладка «Система» → «Установить службу»"
    )


def uninstall_user():
    cfg = ConfigManager()
    if cfg.config.get("password_hash") and not is_admin():
        pwd = simpledialog.askstring("Подтверждение", "Введите пароль для удаления:", show="*")
        if not pwd or not cfg.check_password(pwd):
            if pwd:
                messagebox.showerror("Ошибка", "Неверный пароль!")
            return

    if not messagebox.askyesno("Подтверждение", "Удалить TimeScreen Control полностью?"):
        return

    _stop_monitor_process()

    desktop = Path.home() / "Desktop"
    for name in ["TimeScreen - Настройки.lnk", "TimeScreen - Защита.lnk",
                 "Родительский контроль - Админ.lnk", "Родительский контроль - Защита.lnk"]:
        (desktop / name).unlink(missing_ok=True)

    startup_link = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "TimeScreen.lnk"
    startup_link.unlink(missing_ok=True)

    # Удаляем службу (требуются права админа)
    svc_installed, _ = _check_service_static()
    if svc_installed:
        if is_admin():
            try:
                for _ in range(3):
                    subprocess.run(["sc", "stop", SERVICE_NAME],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    time.sleep(1)
                subprocess.run(["sc", "delete", SERVICE_NAME],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                log("Service deleted")
            except Exception:
                pass
        else:
            # Запрашиваем повышение для удаления службы
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, "--uninstall-service-only", None, 1
            )
            time.sleep(2)  # Даём время на UAC и выполнение
            # Продолжаем удаление даже если UAC отменён — службу можно удалить позже

    # Удаляем флаги и конфиг (игнорируем PermissionError — файлы от SYSTEM)
    for f in (LOCK_FLAG, PID_FILE, CONFIG_FILE, LOG_FILE, AGENT_PID):
        try:
            f.unlink(missing_ok=True)
        except PermissionError:
            pass

    # Удаляем папку
    if INSTALL_DIR.exists():
        my_exe = Path(sys.executable).resolve()
        if my_exe.parent.resolve() == INSTALL_DIR.resolve():
            _run_cleanup_bat(INSTALL_DIR)
        else:
            try:
                shutil.rmtree(str(INSTALL_DIR), ignore_errors=True)
            except Exception:
                _run_cleanup_bat(INSTALL_DIR)

    # Удаляем ProgramData
    programdata_dir = CONFIG_FILE.parent
    try:
        shutil.rmtree(str(programdata_dir), ignore_errors=True)
    except Exception:
        pass

    messagebox.showinfo("Удаление", "TimeScreen Control удалён.")


# ---------------------------------------------------------------------------
# Главное окно (GUI)
# ---------------------------------------------------------------------------

class MainApp:
    def __init__(self):
        self.cfg = ConfigManager()
        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} v{APP_VERSION}")
        self.root.geometry("500x500")
        self.root.resizable(True, True)
        self.root.minsize(460, 460)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TButton", padding=8, font=("Arial", 10))
        style.configure("TLabel", font=("Arial", 10))
        style.configure("TLabelframe.Label", font=("Arial", 11, "bold"))
        style.configure("TNotebook.Tab", font=("Arial", 10, "bold"), padding=(16, 6))

        self._build_ui()
        self._refresh_status()

    def _build_ui(self):
        header = tk.Frame(self.root, bg="#2c3e50", height=50)
        header.pack(fill="x")
        tk.Label(header, text=APP_NAME, font=("Arial", 15, "bold"),
                 bg="#2c3e50", fg="white").pack(pady=3)
        tk.Label(header, text=f"v{APP_VERSION} — Родительский контроль",
                 font=("Arial", 9), bg="#2c3e50", fg="#bdc3c7").pack()

        self.status_var = tk.StringVar()
        status_bar = tk.Frame(self.root, bg="#ecf0f1", height=26)
        status_bar.pack(fill="x", side="bottom")
        tk.Label(status_bar, textvariable=self.status_var, font=("Arial", 10),
                 bg="#ecf0f1", fg="#2c3e50", anchor="w", padx=10).pack(fill="x")

        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=10, pady=10)

        # === Вкладка 1: Настройки ===
        tab1 = tk.Frame(nb, padx=15, pady=15)
        nb.add(tab1, text="  Настройки  ")

        sec_frame = ttk.LabelFrame(tab1, text="Безопасность", padding=10)
        sec_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(sec_frame, text="Пароль администратора:").pack(anchor="w")
        self.pass_entry = ttk.Entry(sec_frame, show="*", font=("Arial", 12))
        self.pass_entry.pack(fill="x", pady=(5, 8))
        ttk.Button(sec_frame, text="Установить / Изменить",
                   command=self._set_password).pack(fill="x")

        sched_frame = ttk.LabelFrame(tab1, text="Расписание доступа", padding=10)
        sched_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(sched_frame, text="Интервалы (ЧЧ:ММ-ЧЧ:ММ через запятую):").pack(anchor="w")
        ttk.Label(sched_frame, text="Пример: 08:00-22:00, 14:00-16:00",
                  font=("Arial", 9), foreground="gray").pack(anchor="w")
        self.sched_entry = ttk.Entry(sched_frame, font=("Arial", 12))
        self.sched_entry.pack(fill="x", pady=(5, 8))
        ttk.Button(sched_frame, text="Сохранить расписание",
                   command=self._save_schedule).pack(fill="x")

        # Контролируемые пользователи
        users_frame = ttk.LabelFrame(tab1, text="Пользователи (Multi-user)", padding=10)
        users_frame.pack(fill="x")
        ttk.Label(users_frame, text="Имена пользователей Windows через запятую:").pack(anchor="w")
        ttk.Label(users_frame, text="Оставьте пустым — контроль всех пользователей",
                  font=("Arial", 9), foreground="gray").pack(anchor="w")
        self.users_entry = ttk.Entry(users_frame, font=("Arial", 12))
        self.users_entry.pack(fill="x", pady=(5, 8))
        ttk.Button(users_frame, text="Сохранить список",
                   command=self._save_users).pack(fill="x")

        # === Вкладка 2: Управление ===
        tab2 = tk.Frame(nb, padx=15, pady=15)
        nb.add(tab2, text="  Управление  ")

        ctrl_frame = ttk.LabelFrame(tab2, text="Защита", padding=10)
        ctrl_frame.pack(fill="x", pady=(0, 10))

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

        ind_frame = ttk.LabelFrame(tab2, text="Индикатор в углу экрана", padding=10)
        ind_frame.pack(fill="x")
        self.show_timer_var = tk.BooleanVar(value=self.cfg.config.get("show_timer", True))
        self.show_timer_cb = ttk.Checkbutton(
            ind_frame, text="Показывать индикатор обратного отсчёта",
            variable=self.show_timer_var, command=self._toggle_show_timer
        )
        self.show_timer_cb.pack(anchor="w")

        # === Вкладка 3: Система ===
        tab3 = tk.Frame(nb, padx=15, pady=15)
        nb.add(tab3, text="  Система  ")

        svc_frame = ttk.LabelFrame(tab3, text="Служба Windows", padding=10)
        svc_frame.pack(fill="x", pady=(0, 10))

        self.svc_status_var = tk.StringVar(value="Проверка...")
        ttk.Label(svc_frame, textvariable=self.svc_status_var,
                  font=("Arial", 10)).pack(anchor="w", pady=(0, 5))

        self.btn_service = tk.Button(svc_frame, text="Установить службу",
                                     font=("Arial", 10), bg="#8e44ad", fg="white",
                                     relief="flat", padx=10, pady=6,
                                     command=self._toggle_service)
        self.btn_service.pack(fill="x", pady=2)

        del_frame = ttk.LabelFrame(tab3, text="Удаление", padding=10)
        del_frame.pack(fill="x")
        tk.Button(del_frame, text="Удалить программу полностью",
                  font=("Arial", 10), bg="#c0392b", fg="white",
                  relief="flat", padx=10, pady=6,
                  command=self._uninstall).pack(fill="x", pady=2)

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

        self.users_entry.delete(0, "end")
        controlled = self.cfg.config.get("controlled_users", [])
        if controlled:
            self.users_entry.insert(0, ", ".join(controlled))

        # Состояние службы
        svc_installed, svc_running = self._check_service_state()
        if svc_installed:
            if svc_running:
                self.svc_status_var.set("Служба: запущена")
                self.btn_service.config(text="Остановить службу")
            else:
                self.svc_status_var.set("Служба: остановлена")
                self.btn_service.config(text="Запустить службу")
        else:
            self.svc_status_var.set("Служба не установлена")
            self.btn_service.config(text="Установить службу")

        # Монитор
        running = svc_running or self._is_monitor_running()
        if running:
            self.btn_start.config(state="disabled")
            self.btn_stop.config(state="normal")
        else:
            self.btn_start.config(state="normal")
            self.btn_stop.config(state="disabled")

    def _is_monitor_running(self) -> bool:
        if not PID_FILE.exists():
            return False
        try:
            pid = int(PID_FILE.read_text().strip())
            result = subprocess.run(
                ["tasklist", "/fi", f"PID eq {pid}", "/fo", "csv", "/nh"],
                capture_output=True, text=True,
                creationflags=_CREATE_NO_WINDOW
            )
            return str(pid) in result.stdout
        except Exception:
            return False

    def _check_service_state(self):
        try:
            result = subprocess.run(
                ["sc", "query", SERVICE_NAME],
                capture_output=True, text=True,
                creationflags=_CREATE_NO_WINDOW
            )
            installed = "FAILED" not in result.stdout and "1060" not in result.stdout
            running = "RUNNING" in result.stdout
            return installed, running
        except Exception:
            return False, False

    def _set_password(self):
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
        messagebox.showinfo("Готово", "Пароль установлен!")
        self._refresh_status()

    def _save_schedule(self):
        if self.cfg.config.get("password_hash"):
            pwd = simpledialog.askstring("Подтверждение", "Введите пароль для изменения расписания:", show="*")
            if not pwd or not self.cfg.check_password(pwd):
                if pwd:
                    messagebox.showerror("Ошибка", "Неверный пароль!")
                return
        raw = self.sched_entry.get().strip()
        intervals = [x.strip() for x in raw.split(",") if x.strip()] if raw else []
        for iv in intervals:
            if "-" not in iv:
                messagebox.showerror("Ошибка", f"Неверный формат: {iv}")
                return
            try:
                for p in iv.split("-"):
                    datetime.datetime.strptime(p.strip(), "%H:%M")
            except ValueError:
                messagebox.showerror("Ошибка", f"Неверное время: {iv}")
                return
        self.cfg.set_intervals(intervals)
        self.cfg.clear_grace()
        messagebox.showinfo("Готово", f"Сохранено: {len(intervals)} интервалов")
        self._refresh_status()

    def _save_users(self):
        if self.cfg.config.get("password_hash"):
            pwd = simpledialog.askstring("Подтверждение", "Введите пароль для изменения списка:", show="*")
            if not pwd or not self.cfg.check_password(pwd):
                if pwd:
                    messagebox.showerror("Ошибка", "Неверный пароль!")
                return
        raw = self.users_entry.get().strip()
        users = [u.strip() for u in raw.split(",") if u.strip()] if raw else []
        self.cfg.set_controlled_users(users)
        msg = f"Контроль: {', '.join(users)}" if users else "Контроль: все пользователи"
        messagebox.showinfo("Готово", msg)
        self._refresh_status()

    def _start_protection(self):
        if not self.cfg.config.get("password_hash"):
            messagebox.showwarning("Внимание", "Сначала установите пароль!")
            return
        if not self.cfg.config.get("intervals"):
            messagebox.showwarning("Внимание", "Сначала задайте расписание!")
            return

        self.cfg.set_enabled(True)
        installed, _ = self._check_service_state()
        if installed:
            # Запускаем службу и проверяем результат
            result = subprocess.run(["sc", "start", SERVICE_NAME],
                                    capture_output=True, text=True,
                                    creationflags=_CREATE_NO_WINDOW)
            # Ждём до 10 секунд с проверкой каждые 2 сек
            running = False
            for _ in range(5):
                time.sleep(2)
                _, running = self._check_service_state()
                if running:
                    break
            if running:
                messagebox.showinfo("Запущено", "Служба запущена. Защита активна.")
            else:
                messagebox.showwarning(
                    "Внимание",
                    f"Служба не запустилась.\n\n{result.stdout.strip()}\n{result.stderr.strip()}\n\n"
                    "Попробуйте открыть вкладку «Система» и установить службу заново."
                )
                return  # Не запускаем агент, если служба не стартанула

        # Запускаем агент (индикатор + экран блокировки), если ещё не запущен
        agent_running = False
        if AGENT_PID.exists():
            try:
                pid = int(AGENT_PID.read_text().strip())
                result = subprocess.run(
                    ["tasklist", "/fi", f"PID eq {pid}", "/fo", "csv", "/nh"],
                    capture_output=True, text=True,
                    creationflags=_CREATE_NO_WINDOW
                )
                agent_running = str(pid) in result.stdout
            except Exception:
                pass
        if not agent_running:
            subprocess.Popen([sys.executable, "--user-agent"], creationflags=0x08000000)
        if not installed:
            messagebox.showinfo("Запущено", "Агент запущен. Защита активна.")
        self._refresh_status()

    def _stop_protection(self):
        pwd = simpledialog.askstring("Подтверждение", "Введите пароль для остановки:", show="*")
        if pwd and self.cfg.check_password(pwd):
            self.cfg.set_enabled(False)
            installed, _ = self._check_service_state()
            if installed:
                subprocess.run(["sc", "stop", SERVICE_NAME],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["taskkill", "/f", "/im", "TimeScreenControl.exe"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            LOCK_FLAG.unlink(missing_ok=True)
            messagebox.showinfo("Стоп", "Защита остановлена.")
            self._refresh_status()
        elif pwd:
            messagebox.showerror("Ошибка", "Неверный пароль!")

    def _toggle_show_timer(self):
        self.cfg.config["show_timer"] = self.show_timer_var.get()
        self.cfg.save()

    def _toggle_service(self):
        installed, running = self._check_service_state()
        if installed:
            if running:
                if not is_admin():
                    ctypes.windll.shell32.ShellExecuteW(
                        None, "runas", sys.executable, "--uninstall-service", None, 1
                    )
                    return
                subprocess.run(["sc", "stop", SERVICE_NAME],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                messagebox.showinfo("Служба", "Служба остановлена.")
            else:
                subprocess.run(["sc", "start", SERVICE_NAME],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                messagebox.showinfo("Служба", "Служба запущена.")
        else:
            self._install_service()
        self._refresh_status()

    def _install_service(self):
        _install_windows_service()
        self._refresh_status()

    def _uninstall(self):
        uninstall_user()
        # Закрываем главное окно после удаления
        self.root.destroy()

    def run(self):
        self.root.mainloop()


# ---------------------------------------------------------------------------
# Точка входа
# ---------------------------------------------------------------------------

def main():
    args = sys.argv[1:]

    if not args:
        app = MainApp()
        app.run()
    elif args[0] == "--lock":
        LockScreen().run()
    elif args[0] == "--timer":
        TimerOverlay()
    elif args[0] == "--monitor":
        run_monitor()
    elif args[0] == "--service-daemon":
        # Режим службы: только монитор времени (headless)
        run_monitor()
    elif args[0] == "--user-agent":
        # Пользовательский агент: таймер + блокировка по флагу
        run_user_agent()
    elif args[0] == "--recovery":
        cfg = ConfigManager()
        if cfg.config.get("_tampered"):
            CONFIG_FILE.unlink(missing_ok=True)
        subprocess.run(["taskkill", "/f", "/im", "TimeScreenControl.exe"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        messagebox.showinfo("Восстановление", "Конфигурация сброшена.\nЗадайте новый пароль и расписание.")
        app = MainApp()
        app.run()
    elif args[0] == "--toggle":
        cfg = ConfigManager()
        if cfg.config.get("password_hash"):
            root = tk.Tk(); root.withdraw()
            pwd = simpledialog.askstring("Подтверждение", "Введите пароль:", show="*")
            root.destroy()
            if not pwd or not cfg.check_password(pwd):
                if pwd:
                    root2 = tk.Tk(); root2.withdraw()
                    messagebox.showerror("Ошибка", "Неверный пароль!")
                    root2.destroy()
                return
        cfg.set_enabled(not cfg.config.get("enabled", True))
        root3 = tk.Tk(); root3.withdraw()
        messagebox.showinfo("Защита", f"Защита {'ВКЛЮЧЕНА' if cfg.config['enabled'] else 'ВЫКЛЮЧЕНА'}.")
        root3.destroy()
    elif args[0] == "--install-service":
        _install_windows_service()
    elif args[0] == "--uninstall-service":
        _uninstall_windows_service()
    elif args[0] == "--uninstall-service-only":
        # Вызывается с правами админа — только удалить службу и выйти
        _delete_service_internal()
        sys.exit(0)
    elif args[0] == "install-user":
        install_user()
    elif args[0] == "uninstall-user":
        uninstall_user()
    else:
        print(f"Unknown command: {args[0]}")


if __name__ == "__main__":
    main()
