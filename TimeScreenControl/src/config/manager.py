"""
TimeScreen Control - Configuration Manager
Single source of truth for all configuration operations.
"""

import json
import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from .paths import CONFIG_PATH, ensure_program_data_exists
from .security import hash_password, verify_password, compute_hash


class ConfigManager:
    """
    Unified configuration manager for all TimeScreen components.
    
    Thread-safe, with integrity checking and automatic migration.
    """
    
    DEFAULT_CONFIG = {
        "password_hash": None,
        "intervals": [],
        "enabled": True,
        "controlled_users": [],
        "show_timer": True,
        "timer_position": (100, 100),
        "grace_until": None,
        "_hash": None,
    }
    
    GRACE_MINUTES = 10
    
    def __init__(self, read_only: bool = False):
        """
        Initialize configuration manager.
        
        Args:
            read_only: If True, save() operations will fail
        """
        self.read_only = read_only
        ensure_program_data_exists()
        self.config = self._load()
    
    def _load(self) -> dict:
        """Load configuration with integrity verification."""
        if not CONFIG_PATH.exists():
            return self.DEFAULT_CONFIG.copy()
        
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
                raw = json.load(f)
            
            # Verify integrity
            stored_hash = raw.pop("_hash", None)
            if stored_hash:
                expected = compute_hash(raw)
                if stored_hash != expected:
                    # Config tampered - enter lockdown mode
                    return {
                        "password_hash": None,
                        "intervals": [],
                        "enabled": True,
                        "controlled_users": [],
                        "show_timer": False,
                        "_tampered": True,
                    }
            
            # Merge with defaults for any missing fields
            config = self.DEFAULT_CONFIG.copy()
            config.update(raw)
            return config
            
        except Exception as e:
            # On any error, return safe defaults
            return self.DEFAULT_CONFIG.copy()
    
    def save(self) -> bool:
        """
        Save configuration with integrity hash.
        
        Returns:
            True if saved successfully, False otherwise
        """
        if self.read_only:
            return False
        
        if self.config.get("_tampered"):
            return False  # Don't save tampered config
        
        try:
            data = self.config.copy()
            data.pop("_tampered", None)
            data["_hash"] = compute_hash(data)
            
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            return True
        except Exception:
            return False
    
    # ==================== Password Management ====================
    
    def has_password(self) -> bool:
        """Check if a password is set."""
        return bool(self.config.get("password_hash"))
    
    def set_password(self, password: str) -> bool:
        """
        Set new admin password.
        
        Args:
            password: Plain text password (min 4 characters)
            
        Returns:
            True if successful, False otherwise
        """
        if len(password) < 4:
            return False
        
        self.config["password_hash"] = hash_password(password)
        return self.save()
    
    def verify_password(self, password: str) -> bool:
        """
        Verify admin password.
        
        Args:
            password: Plain text password to verify
            
        Returns:
            True if correct, False otherwise
        """
        if self.config.get("_tampered"):
            return False
        
        stored_hash = self.config.get("password_hash")
        if not stored_hash:
            return True  # No password set = allow
        
        return verify_password(password, stored_hash)
    
    # ==================== Interval Management ====================
    
    def get_intervals(self) -> List[Dict[str, Any]]:
        """Get all time intervals."""
        return self.config.get("intervals", [])
    
    def add_interval(self, start: str, end: str, days: List[int]) -> bool:
        """
        Add a new time interval.
        
        Args:
            start: Start time in HH:MM format
            end: End time in HH:MM format
            days: List of day indices (0=Monday, 6=Sunday)
            
        Returns:
            True if added successfully, False if invalid
        """
        # Validate times
        try:
            datetime.datetime.strptime(start, "%H:%M")
            datetime.datetime.strptime(end, "%H:%M")
        except ValueError:
            return False
        
        # Validate days
        if not days or not all(0 <= d <= 6 for d in days):
            return False
        
        interval = {
            "start": start,
            "end": end,
            "days": sorted(days),
        }
        
        self.config["intervals"].append(interval)
        return self.save()
    
    def remove_interval(self, index: int) -> bool:
        """Remove interval by index."""
        intervals = self.config.get("intervals", [])
        if 0 <= index < len(intervals):
            intervals.pop(index)
            return self.save()
        return False
    
    def clear_intervals(self) -> bool:
        """Clear all intervals."""
        self.config["intervals"] = []
        return self.save()
    
    # ==================== User Management ====================
    
    def get_controlled_users(self) -> List[str]:
        """Get list of controlled users."""
        return self.config.get("controlled_users", [])
    
    def set_controlled_users(self, users: List[str]) -> bool:
        """Set list of controlled users."""
        self.config["controlled_users"] = [u.strip() for u in users if u.strip()]
        return self.save()
    
    def is_controlled_user(self, username: Optional[str] = None) -> bool:
        """
        Check if current user is controlled.
        
        Args:
            username: Username to check (default: current user)
            
        Returns:
            True if user is controlled, False otherwise
        """
        import os
        current = username or os.environ.get("USERNAME", "")
        controlled = self.config.get("controlled_users", [])
        
        if not controlled:
            return True  # Empty list = control everyone
        
        return current.lower() in [u.lower() for u in controlled]
    
    # ==================== Enable/Disable ====================
    
    def is_enabled(self) -> bool:
        """Check if protection is enabled."""
        return self.config.get("enabled", True)
    
    def set_enabled(self, state: bool) -> bool:
        """Enable or disable protection."""
        self.config["enabled"] = state
        return self.save()
    
    # ==================== Timer Settings ====================
    
    def show_timer(self) -> bool:
        """Check if timer overlay should be shown."""
        return self.config.get("show_timer", True)
    
    def set_show_timer(self, show: bool) -> bool:
        """Show or hide timer overlay."""
        self.config["show_timer"] = show
        return self.save()
    
    def get_timer_position(self) -> tuple:
        """Get timer overlay position."""
        pos = self.config.get("timer_position", (100, 100))
        return tuple(pos) if isinstance(pos, list) else pos
    
    def set_timer_position(self, x: int, y: int) -> bool:
        """Set timer overlay position."""
        self.config["timer_position"] = [x, y]
        return self.save()
    
    # ==================== Grace Period ====================
    
    def set_grace(self) -> bool:
        """Set grace period (10 minutes from now)."""
        until = datetime.datetime.now() + datetime.timedelta(minutes=self.GRACE_MINUTES)
        self.config["grace_until"] = until.isoformat()
        return self.save()
    
    def is_in_grace(self) -> bool:
        """Check if currently in grace period."""
        ts = self.config.get("grace_until")
        if not ts:
            return False
        
        try:
            until = datetime.datetime.fromisoformat(ts)
            return datetime.datetime.now() < until
        except Exception:
            return False
    
    def clear_grace(self) -> bool:
        """Clear grace period."""
        self.config.pop("grace_until", None)
        return self.save()
    
    # ==================== Time Checking ====================
    
    def is_allowed_time(self) -> bool:
        """
        Check if current time is within allowed intervals.
        
        Returns:
            True if usage is allowed, False if blocked
        """
        if self.config.get("_tampered"):
            return False
        
        if not self.config.get("enabled", True):
            return True
        
        intervals = self.config.get("intervals", [])
        if not intervals:
            return True
        
        now = datetime.datetime.now()
        current_time = now.time()
        current_day = now.weekday()  # 0=Monday
        
        for interval in intervals:
            # Check if today is in the interval's days
            if current_day not in interval.get("days", list(range(7))):
                continue
            
            try:
                start = datetime.datetime.strptime(interval["start"], "%H:%M").time()
                end = datetime.datetime.strptime(interval["end"], "%H:%M").time()
                
                if start <= end:
                    # Normal interval (e.g., 08:00-22:00)
                    if start <= current_time <= end:
                        return True
                else:
                    # Overnight interval (e.g., 22:00-08:00)
                    if current_time >= start or current_time <= end:
                        return True
                        
            except (ValueError, KeyError):
                continue
        
        return False
    
    def get_next_event(self) -> tuple:
        """
        Get next lock/unlock event.
        
        Returns:
            Tuple of (seconds_until_event, event_type) or (None, None)
            event_type is "lock" or "unlock"
        """
        intervals = self.config.get("intervals", [])
        if not intervals or not self.config.get("enabled", True):
            return None, None
        
        now_dt = datetime.datetime.now()
        now_t = now_dt.time()
        today = now_dt.date()
        current_day = now_dt.weekday()
        
        next_lock = None
        next_unlock = None
        
        for interval in intervals:
            if current_day not in interval.get("days", list(range(7))):
                continue
            
            try:
                start = datetime.datetime.strptime(interval["start"], "%H:%M").time()
                end = datetime.datetime.strptime(interval["end"], "%H:%M").time()
                
                s_dt = datetime.datetime.combine(today, start)
                e_dt = datetime.datetime.combine(today, end)
                
                # Handle overnight intervals
                if start > end:
                    if now_t >= start or now_t <= end:
                        # Currently in interval
                        if now_t >= start:
                            candidate = e_dt + datetime.timedelta(days=1)
                        else:
                            candidate = e_dt
                        if candidate > now_dt and (next_lock is None or candidate < next_lock):
                            next_lock = candidate
                    else:
                        # Before interval starts
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
                            
            except (ValueError, KeyError):
                continue
        
        allowed = self.is_allowed_time()
        if allowed and next_lock:
            return int((next_lock - now_dt).total_seconds()), "lock"
        elif not allowed and next_unlock:
            return int((next_unlock - now_dt).total_seconds()), "unlock"
        elif not allowed:
            return None, "blocked_no_schedule"
        
        return None, None
