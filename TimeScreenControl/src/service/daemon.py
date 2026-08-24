"""Windows service that enforces TimeScreen rules in the active user session."""

import datetime
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

import servicemanager
import win32event
import win32service
import win32serviceutil

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.manager import ConfigManager
from config.paths import INSTALL_DIR, LOG_PATH, SERVICE_PID, SERVICE_PIPE_NAME


class ServiceLogger:
    def __init__(self, log_path: Path):
        self.log_path = log_path

    def log(self, message: str, level: str = "INFO"):
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_path, "a", encoding="utf-8") as stream:
                stream.write(f"[{datetime.datetime.now().isoformat()}] [{level}] {message}\n")
        except OSError:
            pass


class TimeScreenService(win32serviceutil.ServiceFramework):
    _svc_name_ = "TimeScreenControl"
    _svc_display_name_ = "TimeScreen Control Service"
    _svc_description_ = "Управляет родительским контролем и блокировкой экрана."

    CHECK_INTERVAL_SECONDS = 5

    def __init__(self, args):
        super().__init__(args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.logger = ServiceLogger(LOG_PATH)
        self.lock_screens: Dict[int, dict] = {}
        self._pipe_thread: Optional[threading.Thread] = None
        self._failed_unlocks = []

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.stop_event)
        self._terminate_all_lock_screens()
        try:
            SERVICE_PID.unlink()
        except OSError:
            pass
        self.logger.log("Service stopping")

    def SvcDoRun(self):
        self.ReportServiceStatus(win32service.SERVICE_RUNNING)
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, ""),
        )
        self.logger.log("Service started")
        try:
            SERVICE_PID.parent.mkdir(parents=True, exist_ok=True)
            SERVICE_PID.write_text(str(os.getpid()), encoding="ascii")
        except OSError as exc:
            self.logger.log(f"Failed to write PID: {exc}", "WARNING")

        self._pipe_thread = threading.Thread(target=self._serve_unlock_requests, daemon=True)
        self._pipe_thread.start()

        while True:
            try:
                self._check_and_enforce()
            except Exception as exc:
                self.logger.log(f"Error in enforcement loop: {exc}", "ERROR")
            result = win32event.WaitForSingleObject(self.stop_event, self.CHECK_INTERVAL_SECONDS * 1000)
            if result == win32event.WAIT_OBJECT_0:
                break
        self._terminate_all_lock_screens()

    def _check_and_enforce(self):
        self._clean_finished_processes()
        identity = self._get_active_identity()
        if identity is None:
            return
        session_id, username = identity
        cfg = ConfigManager(read_only=True)

        # Crucial multi-user boundary: only the active session whose username is
        # explicitly selected is enforced; an empty selection controls nobody.
        should_lock = cfg.should_block_user(username)
        if should_lock:
            self._ensure_lock_screen(session_id, username)
        else:
            self._terminate_lock_screen(session_id)

    def _get_active_identity(self) -> Optional[Tuple[int, str]]:
        try:
            import win32ts

            session_id = win32ts.WTSGetActiveConsoleSessionId()
            if session_id == 0xFFFFFFFF:
                return None
            username = win32ts.WTSQuerySessionInformation(None, session_id, win32ts.WTSUserName)
            if not username:
                self.logger.log(f"Session {session_id} has no user", "WARNING")
                return None
            return session_id, username
        except Exception as exc:
            self.logger.log(f"Failed to query active user: {exc}", "WARNING")
            return None

    def _ensure_lock_screen(self, session_id: int, username: str):
        if self._is_lock_screen_running(session_id):
            return
        try:
            if getattr(sys, "frozen", False):
                executable = INSTALL_DIR / "TimeScreenControl.exe"
                if not executable.exists():
                    raise FileNotFoundError(f"GUI executable not found: {executable}")
                self._launch_in_session(session_id, [str(executable), "--locker-mode"], INSTALL_DIR)
            else:
                script = Path(__file__).parent.parent / "gui" / "lock_screen.py"
                process = subprocess.Popen([sys.executable, str(script)])
                self.lock_screens[session_id] = {"process": process, "pid": process.pid, "handle": None}
            self.logger.log(f"Lock screen launched for {username}, session {session_id}")
        except Exception as exc:
            self.logger.log(f"Failed to launch lock screen for session {session_id}: {exc}", "ERROR")

    def _launch_in_session(self, session_id: int, command, working_dir: Path):
        import win32api
        import win32con
        import win32process
        import win32profile
        import win32ts

        token = win32ts.WTSQueryUserToken(session_id)
        environment = None
        try:
            environment = win32profile.CreateEnvironmentBlock(token, False)
            startup = win32process.STARTUPINFO()
            startup.lpDesktop = r"winsta0\default"
            process_handle, thread_handle, pid, _ = win32process.CreateProcessAsUser(
                token, None, subprocess.list2cmdline(command), None, None, False,
                win32con.CREATE_UNICODE_ENVIRONMENT | win32con.CREATE_NEW_PROCESS_GROUP,
                environment, str(working_dir), startup,
            )
            win32api.CloseHandle(thread_handle)
            self.lock_screens[session_id] = {"process": None, "pid": pid, "handle": process_handle}
        finally:
            if environment is not None:
                win32profile.DestroyEnvironmentBlock(environment)
            win32api.CloseHandle(token)

    def _is_lock_screen_running(self, session_id: int) -> bool:
        entry = self.lock_screens.get(session_id)
        if not entry:
            return False
        if entry["process"] is not None:
            return entry["process"].poll() is None
        return win32event.WaitForSingleObject(entry["handle"], 0) == win32event.WAIT_TIMEOUT

    def _clean_finished_processes(self):
        for session_id in list(self.lock_screens):
            if not self._is_lock_screen_running(session_id):
                self._close_process_entry(session_id, terminate=False)

    def _terminate_lock_screen(self, session_id: int):
        if session_id in self.lock_screens:
            self._close_process_entry(session_id, terminate=True)
            self.logger.log(f"Lock screen terminated for session {session_id}")

    def _close_process_entry(self, session_id: int, terminate: bool):
        entry = self.lock_screens.pop(session_id, None)
        if not entry:
            return
        if entry["process"] is not None:
            if terminate and entry["process"].poll() is None:
                entry["process"].terminate()
            return
        import win32api
        import win32process
        try:
            if terminate and win32event.WaitForSingleObject(entry["handle"], 0) == win32event.WAIT_TIMEOUT:
                win32process.TerminateProcess(entry["handle"], 0)
        finally:
            win32api.CloseHandle(entry["handle"])

    def _terminate_all_lock_screens(self):
        for session_id in list(self.lock_screens):
            try:
                self._close_process_entry(session_id, terminate=True)
            except Exception as exc:
                self.logger.log(f"Failed to terminate session {session_id}: {exc}", "WARNING")

    @staticmethod
    def _pipe_security_attributes():
        import ntsecuritycon
        import pywintypes
        import win32security

        acl = win32security.ACL()
        for sid_type in (
            win32security.WinLocalSystemSid,
            win32security.WinBuiltinAdministratorsSid,
            win32security.WinAuthenticatedUserSid,
        ):
            sid = win32security.CreateWellKnownSid(sid_type, None)
            acl.AddAccessAllowedAce(win32security.ACL_REVISION, ntsecuritycon.GENERIC_READ | ntsecuritycon.GENERIC_WRITE, sid)
        descriptor = win32security.SECURITY_DESCRIPTOR()
        descriptor.SetSecurityDescriptorDacl(True, acl, False)
        attributes = pywintypes.SECURITY_ATTRIBUTES()
        attributes.SECURITY_DESCRIPTOR = descriptor
        return attributes

    def _serve_unlock_requests(self):
        """Verify TimeScreen passwords inside SYSTEM before granting grace."""
        import pywintypes
        import win32file
        import win32pipe

        while win32event.WaitForSingleObject(self.stop_event, 0) != win32event.WAIT_OBJECT_0:
            pipe = None
            try:
                pipe = win32pipe.CreateNamedPipe(
                    SERVICE_PIPE_NAME,
                    win32pipe.PIPE_ACCESS_DUPLEX,
                    win32pipe.PIPE_TYPE_MESSAGE | win32pipe.PIPE_READMODE_MESSAGE | win32pipe.PIPE_WAIT
                    | getattr(win32pipe, "PIPE_REJECT_REMOTE_CLIENTS", 0x8),
                    win32pipe.PIPE_UNLIMITED_INSTANCES, 4096, 4096, 0,
                    self._pipe_security_attributes(),
                )
                try:
                    win32pipe.ConnectNamedPipe(pipe, None)
                except pywintypes.error as exc:
                    if exc.winerror != 535:  # ERROR_PIPE_CONNECTED
                        raise
                _, raw = win32file.ReadFile(pipe, 4096)
                request = json.loads(raw.decode("utf-8"))
                response = self._handle_unlock_request(request)
                win32file.WriteFile(pipe, json.dumps(response, ensure_ascii=False).encode("utf-8"))
            except Exception as exc:
                self.logger.log(f"Pipe request failed: {exc}", "WARNING")
            finally:
                if pipe is not None:
                    try:
                        win32pipe.DisconnectNamedPipe(pipe)
                    except Exception:
                        pass
                    win32file.CloseHandle(pipe)

    def _handle_unlock_request(self, request: dict) -> dict:
        now = time.monotonic()
        self._failed_unlocks = [attempt for attempt in self._failed_unlocks if now - attempt < 60]
        if len(self._failed_unlocks) >= 5:
            return {"ok": False, "error": "Слишком много попыток. Повторите через минуту"}
        if request.get("command") != "grant_grace" or not isinstance(request.get("password"), str):
            return {"ok": False, "error": "Недопустимая команда"}
        cfg = ConfigManager(read_only=False)
        if not cfg.verify_password(request["password"]):
            self._failed_unlocks.append(now)
            time.sleep(1)
            return {"ok": False, "error": "Неверный пароль"}
        if not cfg.set_grace():
            return {"ok": False, "error": cfg.last_error or "Не удалось сохранить grace-период"}
        self._failed_unlocks.clear()
        return {"ok": True}


def run_service():
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(TimeScreenService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(TimeScreenService)


if __name__ == "__main__":
    run_service()
