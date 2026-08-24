"""
TimeScreen Control - Main Entry Point

Usage:
  TimeScreenControl.exe              # Open settings GUI
  TimeScreenControl.exe --service    # Run as Windows service (SYSTEM account)
  TimeScreenControl.exe --version    # Show version
  TimeScreenControl.exe --help       # Show help

For installation, run install.bat as Administrator.
"""

import sys
import os
import ctypes
import subprocess
from pathlib import Path

def get_base_path():
    """Get base path for both development and PyInstaller bundle"""
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        return Path(sys.executable).parent
    else:
        # Running as script
        return Path(__file__).parent


def is_windows_admin():
    """Return whether the current process has an elevated administrator token."""
    if os.name != "nt":
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_settings_elevated():
    """Settings write the protected machine-wide config and therefore require UAC."""
    if getattr(sys, "frozen", False):
        executable = sys.executable
        parameters = ""
    else:
        executable = sys.executable
        parameters = subprocess.list2cmdline([str(Path(__file__).resolve())])
    result = ctypes.windll.shell32.ShellExecuteW(None, "runas", executable, parameters, None, 1)
    return result > 32

def main():
    """Main entry point"""
    base_path = get_base_path()
    
    # Add appropriate paths for module imports
    if (base_path / "src").exists():
        sys.path.insert(0, str(base_path / "src"))
    else:
        sys.path.insert(0, str(base_path))
    
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "--service":
            # Run as Windows Service (for pywin32 service wrapper)
            from service.daemon import run_service
            run_service()
        elif cmd == "--locker-mode":
            # Run lock screen directly (called by service)
            from gui.lock_screen import run_lock_screen
            run_lock_screen()
        elif cmd == "--timer-mode":
            from gui.timer_overlay import run_timer_overlay
            run_timer_overlay()
        elif cmd == "--grant-grace":
            from config.manager import ConfigManager
            if not is_windows_admin():
                print("Administrator privileges are required")
                sys.exit(5)
            sys.exit(0 if ConfigManager(read_only=False).set_grace() else 1)
        elif cmd == "--version":
            print("TimeScreen Control v3.0")
        elif cmd == "--help":
            print("""
TimeScreen Control - Parental Control System

Usage:
  TimeScreenControl.exe              # Open settings (admin auth required)
  TimeScreenControl.exe --service    # Run as Windows service
  TimeScreenControl.exe --locker-mode # Run lock screen (internal use)
  TimeScreenControl.exe --timer-mode # Run timer overlay (internal use)
  TimeScreenControl.exe --grant-grace # Start grace period (internal UAC helper)
  TimeScreenControl.exe --version    # Show version
  TimeScreenControl.exe --help       # Show this help

For installation, run install.bat as Administrator.
            """)
        else:
            print(f"Unknown command: {cmd}")
            print("Use --help for usage information")
            sys.exit(1)
    else:
        # Launch settings GUI
        if not is_windows_admin():
            if not relaunch_settings_elevated():
                sys.exit(5)
            return
        from gui.app import SettingsApp
        app = SettingsApp()
        app.run()

if __name__ == "__main__":
    main()
