"""
TimeScreen Control - Windows Service Daemon
Monitors time and enforces restrictions.
Properly integrated with pywin32 service framework.
"""

import sys
import os
import time
import datetime
import subprocess
import threading
import win32serviceutil
import win32service
import win32event
import servicemanager
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.manager import ConfigManager
from config.paths import LOG_PATH, SERVICE_PID


class ServiceLogger:
    """Simple file logger for the service."""
    
    def __init__(self, log_path: Path):
        self.log_path = log_path
    
    def log(self, message: str, level: str = "INFO"):
        """Log a message with timestamp."""
        try:
            timestamp = datetime.datetime.now().isoformat()
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] [{level}] {message}\n")
        except Exception:
            pass  # Don't fail on logging errors


class TimeScreenService(win32serviceutil.ServiceFramework):
    """
    Windows service that monitors time and enforces restrictions.
    
    Features:
    - Runs in background checking time every minute
    - Launches lock screen when time is up
    - Respects grace period
    - Logs all actions
    - Properly integrated with Windows Service Control Manager
    """
    
    _svc_name_ = "TimeScreenControl"
    _svc_display_name_ = "TimeScreen Control Service"
    _svc_description_ = "Управляет родительским контролем и блокировкой экрана."
    
    CHECK_INTERVAL_SECONDS = 60  # Check every minute
    
    def __init__(self, args):
        super().__init__(args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.cfg = ConfigManager(read_only=True)
        self.logger = ServiceLogger(LOG_PATH)
        self.lock_screen_process = None
        self._last_lock_time = None
    
    def SvcStop(self):
        """Called when service is being stopped."""
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.stop_event)
        
        # Kill lock screen if running
        if self.lock_screen_process:
            try:
                self.lock_screen_process.terminate()
            except Exception:
                pass
        
        # Remove PID file
        try:
            if SERVICE_PID.exists():
                SERVICE_PID.unlink()
        except Exception:
            pass
        
        self.logger.log("Service stopping")
        self.logger.log("Service stopped")
    
    def SvcDoRun(self):
        """Called when service is started."""
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, '')
        )
        
        self.logger.log("Service started")
        
        # Write PID file
        try:
            SERVICE_PID.parent.mkdir(parents=True, exist_ok=True)
            with open(SERVICE_PID, "w") as f:
                f.write(str(os.getpid()))
        except Exception as e:
            self.logger.log(f"Failed to write PID: {e}", "WARNING")
        
        # Main monitoring loop
        while True:
            # Wait for stop event or timeout
            rc = win32event.WaitForSingleObject(self.stop_event, self.CHECK_INTERVAL_SECONDS * 1000)
            
            if rc == win32event.WAIT_OBJECT_0:
                break
            
            try:
                self._check_and_enforce()
            except KeyboardInterrupt:
                self.logger.log("Interrupted by user")
                break
            except Exception as e:
                self.logger.log(f"Error in main loop: {e}", "ERROR")
                time.sleep(10)  # Sleep briefly on error
        
        self.SvcStop()
    
    def _check_and_enforce(self):
        """Check current time and enforce restrictions if needed."""
        # Check if protection is enabled
        if not self.cfg.is_enabled():
            self.logger.log("Protection disabled, skipping check")
            return
        
        # Check if current user is controlled
        if not self.cfg.is_controlled_user():
            self.logger.log("Current user not in controlled list, skipping")
            return
        
        # Check if in grace period
        if self.cfg.is_in_grace():
            self.logger.log("In grace period, allowing access")
            if self.lock_screen_process:
                self._unlock_screen()
            return
        
        # Check if current time is allowed
        allowed = self.cfg.is_allowed_time()
        
        if allowed:
            # Time is allowed - ensure screen is unlocked
            if self.lock_screen_process:
                self._unlock_screen()
            self.logger.log("Time is allowed, no action needed")
        else:
            # Time is NOT allowed - lock screen if not already locked
            if not self.lock_screen_process or self.lock_screen_process.poll() is not None:
                self._lock_screen()
            else:
                self.logger.log("Already locked, no action needed")
    
    def _lock_screen(self):
        """Launch the lock screen."""
        try:
            # Get path to current executable
            if getattr(sys, 'frozen', False):
                # Running as compiled executable
                exe_path = sys.executable
                cmd = [exe_path, "--locker-mode"]
            else:
                # Running as script
                lock_screen_path = Path(__file__).parent / "gui" / "lock_screen.py"
                cmd = [sys.executable, str(lock_screen_path)]
            
            # Start lock screen process
            self.lock_screen_process = subprocess.Popen(
                cmd,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            )
            
            self._last_lock_time = datetime.datetime.now()
            self.logger.log(f"Lock screen launched (PID: {self.lock_screen_process.pid})")
            
        except Exception as e:
            self.logger.log(f"Failed to launch lock screen: {e}", "ERROR")
    
    def _unlock_screen(self):
        """Terminate the lock screen process."""
        try:
            if self.lock_screen_process:
                self.lock_screen_process.terminate()
                self.lock_screen_process = None
                self.logger.log("Lock screen terminated")
        except Exception as e:
            self.logger.log(f"Failed to terminate lock screen: {e}", "ERROR")


def run_service():
    """Entry point for running as a service."""
    win32serviceutil.HandleCommandLine(TimeScreenService)


if __name__ == "__main__":
    run_service()
