"""
TimeScreen Control - Windows Service Entry Point
Minimal entry point for onedir PyInstaller build.
Avoids onefile PID-change issue (Error 1053).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from service.daemon import run_service

if __name__ == "__main__":
    run_service()
