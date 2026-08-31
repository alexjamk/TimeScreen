"""
TimeScreen Control - Path Constants
All paths are centralized here for easy maintenance.
"""

import os
from pathlib import Path

# ProgramData location (all users, requires admin to modify)
PROGRAM_DATA = Path(os.environ.get("PROGRAMDATA", "C:\\ProgramData")) / "TimeScreen"

# Configuration file
CONFIG_PATH = PROGRAM_DATA / "pc_config.json"
INTEGRITY_KEY_PATH = PROGRAM_DATA / "integrity.key"
CONFIG_LOCK_PATH = PROGRAM_DATA / "config.lock"

# Log file
LOG_PATH = PROGRAM_DATA / "service.log"

# Named Mutex for lock state (more secure than file flag)
LOCK_MUTEX_NAME = "Global\\TimeScreenLock"

# PID files. The timer PID is per-user and must not make the shared config writable.
SERVICE_PID = PROGRAM_DATA / "service.pid"
BREAK_STATE_PATH = PROGRAM_DATA / "break_state.json"
LOCAL_APP_DATA = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
USER_DATA = LOCAL_APP_DATA / "TimeScreen"
AGENT_PID = USER_DATA / "agent.pid"
TIMER_STATE_PATH = USER_DATA / "timer_state.json"

# Local authenticated command channel exposed by the SYSTEM service.
SERVICE_PIPE_NAME = r"\\.\pipe\TimeScreenControl"

# Installation directory (Program Files for all users)
INSTALL_DIR = Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "TimeScreenControl"


def ensure_program_data_exists() -> None:
    """Create ProgramData directory if it doesn't exist"""
    PROGRAM_DATA.mkdir(parents=True, exist_ok=True)
