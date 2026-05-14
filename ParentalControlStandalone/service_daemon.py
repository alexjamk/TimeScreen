"""
TimeScreen Service Daemon — minimal, no GUI, runs in Session 0.
Built as console EXE for Windows service. Registers with SCM via ctypes.
"""

import json
import os
import sys
import time
import hashlib
import datetime
import subprocess
import ctypes
from ctypes import wintypes, byref, POINTER, WINFUNCTYPE
from pathlib import Path

# ---------------------------------------------------------------------------
# Windows Service constants & types
# ---------------------------------------------------------------------------
SERVICE_WIN32_OWN_PROCESS = 0x00000010
SERVICE_ACCEPT_STOP       = 0x00000001
SERVICE_RUNNING           = 0x00000004
SERVICE_STOPPED           = 0x00000001
SERVICE_CONTROL_STOP      = 0x00000001

class SERVICE_STATUS(ctypes.Structure):
    _fields_ = [
        ("dwServiceType",             wintypes.DWORD),
        ("dwCurrentState",            wintypes.DWORD),
        ("dwControlsAccepted",        wintypes.DWORD),
        ("dwWin32ExitCode",           wintypes.DWORD),
        ("dwServiceSpecificExitCode", wintypes.DWORD),
        ("dwCheckPoint",              wintypes.DWORD),
        ("dwWaitHint",                wintypes.DWORD),
    ]

class SERVICE_TABLE_ENTRY(ctypes.Structure):
    _fields_ = [
        ("lpServiceName", wintypes.LPWSTR),
        ("lpServiceProc", ctypes.c_void_p),  # LPSERVICE_MAIN_FUNCTIONW
    ]

SERVICE_MAIN_FUNCTION = WINFUNCTYPE(None, wintypes.DWORD, POINTER(wintypes.LPWSTR))

# Globals for service handler
g_status_handle = None

# ---------------------------------------------------------------------------
# Config paths
# ---------------------------------------------------------------------------
SERVICE_NAME = "TimeScreenControl"
CONFIG_FILE  = Path(os.environ.get("PROGRAMDATA", "C:\\ProgramData")) / "TimeScreen" / "pc_config.json"
LOCK_FLAG    = Path(os.environ.get("PROGRAMDATA", "C:\\ProgramData")) / "TimeScreen" / "lock_flag"
PID_FILE     = Path(os.environ.get("PROGRAMDATA", "C:\\ProgramData")) / "TimeScreen" / "monitor.pid"
AGENT_PID    = Path(os.environ.get("PROGRAMDATA", "C:\\ProgramData")) / "TimeScreen" / "agent.pid"
LOG_FILE     = Path(os.environ.get("PROGRAMDATA", "C:\\ProgramData")) / "TimeScreen" / "service.log"
INSTALL_DIR  = Path(os.environ["LOCALAPPDATA"]) / "TimeScreen"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def log(msg: str) -> None:
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{stamp}] {msg}\n")
    except Exception:
        pass

class ConfigManager:
    def __init__(self):
        self.config = self.load()

    def load(self) -> dict:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                raw.pop("_hash", None)
                return raw
            except Exception:
                pass
        return {"password_hash": None, "intervals": [], "enabled": True, "controlled_users": []}

    def is_in_grace(self) -> bool:
        ts = self.config.get("grace_until")
        if not ts:
            return False
        try:
            until = datetime.datetime.fromisoformat(ts)
            return datetime.datetime.now() < until
        except Exception:
            return False

    def is_controlled_user(self) -> bool:
        controlled = self.config.get("controlled_users", [])
        if not controlled:
            return True
        current = os.environ.get("USERNAME", "")
        return current.lower() in [u.lower() for u in controlled]

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

def _restart_agent():
    if not AGENT_PID.exists():
        return
    try:
        pid = int(AGENT_PID.read_text().strip())
        result = subprocess.run(
            ["tasklist", "/fi", f"PID eq {pid}", "/fo", "csv", "/nh"],
            capture_output=True, text=True
        )
        if str(pid) not in result.stdout:
            log("Agent dead – restarting via schtasks")
            agent_vbs = INSTALL_DIR / "run_agent.vbs"
            if agent_vbs.exists():
                subprocess.run(["schtasks", "/create", "/tn", "TimeScreenAgentRestart",
                               "/tr", f'wscript.exe "{agent_vbs}"',
                               "/sc", "once", "/st", "00:00", "/it", "/f"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.run(["schtasks", "/run", "/tn", "TimeScreenAgentRestart"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.run(["schtasks", "/delete", "/tn", "TimeScreenAgentRestart", "/f"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Service Control Handler
# ---------------------------------------------------------------------------

def _report_status(state: int, exit_code: int = 0, wait_hint: int = 0):
    global g_status_handle
    if g_status_handle is None:
        return
    status = SERVICE_STATUS()
    status.dwServiceType = SERVICE_WIN32_OWN_PROCESS
    status.dwCurrentState = state
    status.dwWin32ExitCode = exit_code
    status.dwWaitHint = wait_hint
    if state == SERVICE_RUNNING:
        status.dwControlsAccepted = SERVICE_ACCEPT_STOP
    ctypes.windll.advapi32.SetServiceStatus(g_status_handle, byref(status))

@WINFUNCTYPE(wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.LPVOID)
def _handler_ex(dwControl, dwEventType, lpEventData, lpContext):
    if dwControl == SERVICE_CONTROL_STOP:
        _report_status(SERVICE_STOPPED)
        # Даём монитору завершиться через глобальный флаг
        return 0  # NO_ERROR
    return 1  # ERROR_CALL_NOT_IMPLEMENTED

# ---------------------------------------------------------------------------
# Service Main
# ---------------------------------------------------------------------------

_run_monitor = True

@SERVICE_MAIN_FUNCTION
def _service_main(dwArgs, lpArgs):
    global g_status_handle, _run_monitor
    g_status_handle = ctypes.windll.advapi32.RegisterServiceCtrlHandlerExW(
        SERVICE_NAME, _handler_ex, None
    )
    if not g_status_handle:
        return
    _report_status(SERVICE_RUNNING)

    # --- Монитор ---
    try:
        PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text(str(os.getpid()))
    except Exception:
        pass
    log("Service monitor started")
    loop_count = 0
    try:
        while _run_monitor:
            loop_count += 1
            cfg = ConfigManager()
            if not cfg.config.get("enabled", True):
                time.sleep(5)
                continue
            if loop_count % 6 == 0:
                _restart_agent()
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
        log("Service monitor stopped")
    _report_status(SERVICE_STOPPED)


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

def main():
    if "--service-daemon" not in sys.argv and "--service" not in sys.argv:
        # Запуск не от SCM — просто монитор (для тестирования)
        _service_main(0, None)
    else:
        # Запуск от SCM
        table = (SERVICE_TABLE_ENTRY * 2)()
        table[0].lpServiceName = SERVICE_NAME
        table[0].lpServiceProc = ctypes.cast(_service_main, ctypes.c_void_p).value
        table[1].lpServiceName = None
        table[1].lpServiceProc = 0

        if not ctypes.windll.advapi32.StartServiceCtrlDispatcherW(
            ctypes.byref(table[0])
        ):
            # Fallback: run without SCM
            _service_main(0, None)


if __name__ == "__main__":
    main()
