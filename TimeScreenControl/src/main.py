"""
TimeScreen Control - Main Entry Point
"""

import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

def main():
    """Main entry point"""
    from gui.app import SettingsApp
    
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "--service":
            from service.daemon import run_service
            run_service()
        elif cmd == "--version":
            print("TimeScreen Control v3.0")
        elif cmd == "--help":
            print("""
TimeScreen Control - Parental Control System

Usage:
  TimeScreenControl.exe              # Open settings (admin auth required)
  TimeScreenControl.exe --service    # Run as Windows service
  TimeScreenControl.exe --version    # Show version
  TimeScreenControl.exe --help       # Show this help

For installation, run install.bat as Administrator.
            """)
        else:
            print(f"Unknown command: {cmd}")
            print("Use --help for usage information")
    else:
        # Launch settings GUI
        app = SettingsApp()
        app.run()

if __name__ == "__main__":
    main()
