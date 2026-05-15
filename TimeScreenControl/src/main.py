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
from pathlib import Path

def get_base_path():
    """Get base path for both development and PyInstaller bundle"""
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        return Path(sys.executable).parent
    else:
        # Running as script
        return Path(__file__).parent

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
        elif cmd == "--version":
            print("TimeScreen Control v3.0")
        elif cmd == "--help":
            print("""
TimeScreen Control - Parental Control System

Usage:
  TimeScreenControl.exe              # Open settings (admin auth required)
  TimeScreenControl.exe --service    # Run as Windows service
  TimeScreenControl.exe --locker-mode # Run lock screen (internal use)
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
        from gui.app import SettingsApp
        app = SettingsApp()
        app.run()

if __name__ == "__main__":
    main()
