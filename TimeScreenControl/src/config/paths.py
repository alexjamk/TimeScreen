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

# Log file
LOG_PATH = PROGRAM_DATA / "service.log"

# Named Mutex for lock state (more secure than file flag)
LOCK_MUTEX_NAME = "Global\\TimeScreenLock"

# PID files
SERVICE_PID = PROGRAM_DATA / "service.pid"
AGENT_PID = PROGRAM_DATA / "agent.pid"

# Installation directory (Program Files for all users)
INSTALL_DIR = Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "TimeScreenControl"


def ensure_program_data_exists() -> None:
    """Create ProgramData directory if it doesn't exist"""
    PROGRAM_DATA.mkdir(parents=True, exist_ok=True)
