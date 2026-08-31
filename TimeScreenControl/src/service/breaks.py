"""Persistent per-user work/break cycle accounting for the SYSTEM service."""

import datetime
import json
import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

from config.paths import BREAK_STATE_PATH


NOTIFICATION_MINUTES = (10, 5, 1)


@dataclass
class BreakStatus:
    in_break: bool = False
    break_remaining_seconds: int = 0
    work_remaining_seconds: Optional[int] = None
    notifications: List[int] = field(default_factory=list)


class BreakTracker:
    """Count eligible active-session time and persist independent user cycles."""

    MAX_COUNTED_GAP_SECONDS = 15.0
    SAVE_INTERVAL_SECONDS = 30.0

    def __init__(
        self,
        state_path: Path = BREAK_STATE_PATH,
        wall_clock: Callable[[], datetime.datetime] = datetime.datetime.now,
        monotonic_clock: Callable[[], float] = time.monotonic,
    ):
        self.state_path = state_path
        self.wall_clock = wall_clock
        self.monotonic_clock = monotonic_clock
        self.state = self._load()
        self._last_user: Optional[str] = None
        self._last_monotonic: Optional[float] = None
        self._last_save_monotonic = self.monotonic_clock()
        self._dirty = False

    @staticmethod
    def normalize_username(username: str) -> str:
        value = (username or "").strip().replace("/", "\\")
        return value.rsplit("\\", 1)[-1].casefold()

    @staticmethod
    def _empty_state() -> dict:
        return {"version": 1, "policy": None, "users": {}}

    def _load(self) -> dict:
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
            if (not isinstance(raw, dict) or raw.get("version") != 1
                    or not isinstance(raw.get("users"), dict)):
                return self._empty_state()
            return raw
        except (OSError, ValueError, TypeError):
            return self._empty_state()

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temp_name = tempfile.mkstemp(
            prefix="break_state.", suffix=".tmp", dir=str(self.state_path.parent)
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(self.state, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_name, self.state_path)
            self._dirty = False
            self._last_save_monotonic = self.monotonic_clock()
        finally:
            try:
                if os.path.exists(temp_name):
                    os.unlink(temp_name)
            except OSError:
                pass

    def _save_if_needed(self, force: bool = False) -> None:
        if not self._dirty:
            return
        if force or self.monotonic_clock() - self._last_save_monotonic >= self.SAVE_INTERVAL_SECONDS:
            try:
                self._save()
            except OSError:
                pass

    def _elapsed_for(self, username: str, monotonic_now: float) -> float:
        elapsed = 0.0
        if self._last_user == username and self._last_monotonic is not None:
            elapsed = max(0.0, monotonic_now - self._last_monotonic)
            if elapsed > self.MAX_COUNTED_GAP_SECONDS:
                elapsed = 0.0
        self._last_user = username
        self._last_monotonic = monotonic_now
        return elapsed

    @staticmethod
    def _parse_until(value) -> Optional[datetime.datetime]:
        try:
            return datetime.datetime.fromisoformat(value) if value else None
        except (TypeError, ValueError):
            return None

    def update(
        self,
        username: str,
        enabled: bool,
        eligible_for_work: bool,
        work_minutes: int,
        break_minutes: int,
        now: Optional[datetime.datetime] = None,
        monotonic_now: Optional[float] = None,
    ) -> BreakStatus:
        now = now or self.wall_clock()
        monotonic_now = self.monotonic_clock() if monotonic_now is None else monotonic_now
        key = self.normalize_username(username)
        elapsed = self._elapsed_for(key, monotonic_now)
        policy = {
            "enabled": bool(enabled),
            "work_minutes": int(work_minutes),
            "break_minutes": int(break_minutes),
        }

        if self.state.get("policy") != policy:
            self.state = {"version": 1, "policy": policy, "users": {}}
            elapsed = 0.0
            self._dirty = True
            self._save_if_needed(force=True)

        if not enabled or not key:
            self._save_if_needed()
            return BreakStatus()

        users: Dict[str, dict] = self.state.setdefault("users", {})
        user_state = users.get(key)
        if not isinstance(user_state, dict):
            user_state = None
        if user_state is None:
            user_state = {
                "work_seconds": 0.0,
                "break_until": None,
                "notified": [],
            }
            users[key] = user_state
            self._dirty = True
        break_until = self._parse_until(user_state.get("break_until"))
        if break_until and break_until > now:
            remaining = max(1, int((break_until - now).total_seconds()))
            self._save_if_needed()
            return BreakStatus(in_break=True, break_remaining_seconds=remaining)
        if break_until:
            user_state.update(work_seconds=0.0, break_until=None, notified=[])
            elapsed = 0.0
            self._dirty = True

        limit_seconds = int(work_minutes) * 60
        try:
            previous_work = max(0.0, float(user_state.get("work_seconds", 0.0)))
        except (TypeError, ValueError):
            previous_work = 0.0
            user_state["work_seconds"] = 0.0
            self._dirty = True
        if eligible_for_work:
            user_state["work_seconds"] = min(limit_seconds, previous_work + elapsed)
            if user_state["work_seconds"] != previous_work:
                self._dirty = True

        work_seconds = float(user_state.get("work_seconds", 0.0))
        if work_seconds >= limit_seconds:
            until = now + datetime.timedelta(minutes=int(break_minutes))
            user_state.update(work_seconds=0.0, break_until=until.isoformat(), notified=[])
            self._dirty = True
            self._save_if_needed(force=True)
            return BreakStatus(
                in_break=True,
                break_remaining_seconds=int(break_minutes) * 60,
            )

        remaining = max(0, int(limit_seconds - work_seconds))
        notified = {int(value) for value in user_state.get("notified", []) if isinstance(value, int)}
        notifications = []
        if eligible_for_work:
            for threshold in NOTIFICATION_MINUTES:
                if threshold <= work_minutes and remaining <= threshold * 60 and threshold not in notified:
                    notifications.append(threshold)
                    notified.add(threshold)
            if notifications:
                user_state["notified"] = sorted(notified, reverse=True)
                self._dirty = True
                self._save_if_needed(force=True)
        self._save_if_needed()
        return BreakStatus(work_remaining_seconds=remaining, notifications=notifications)

    def active_break_remaining(self, username: str, now: Optional[datetime.datetime] = None) -> int:
        key = self.normalize_username(username)
        user_state = self.state.get("users", {}).get(key, {})
        if not isinstance(user_state, dict):
            return 0
        until = self._parse_until(user_state.get("break_until"))
        current = now or self.wall_clock()
        return max(0, int((until - current).total_seconds())) if until and until > current else 0

    def close(self) -> None:
        self._save_if_needed(force=True)


def get_active_break_remaining(
    username: str,
    now: Optional[datetime.datetime] = None,
    state_path: Path = BREAK_STATE_PATH,
) -> int:
    """Read-only helper used by user-session UI processes."""
    tracker = BreakTracker(state_path=state_path)
    return tracker.active_break_remaining(username, now)


def get_break_cycle_status(
    username: str,
    work_minutes: int,
    break_minutes: int,
    now: Optional[datetime.datetime] = None,
    state_path: Path = BREAK_STATE_PATH,
) -> BreakStatus:
    """Read the persisted cycle for timer/lock UI without modifying it."""
    tracker = BreakTracker(state_path=state_path)
    policy = tracker.state.get("policy")
    expected = {
        "enabled": True,
        "work_minutes": int(work_minutes),
        "break_minutes": int(break_minutes),
    }
    if policy != expected:
        return BreakStatus(work_remaining_seconds=int(work_minutes) * 60)
    remaining_break = tracker.active_break_remaining(username, now)
    if remaining_break:
        return BreakStatus(in_break=True, break_remaining_seconds=remaining_break)
    key = tracker.normalize_username(username)
    user_state = tracker.state.get("users", {}).get(key, {})
    if not isinstance(user_state, dict):
        user_state = {}
    try:
        work_seconds = max(0.0, float(user_state.get("work_seconds", 0.0)))
    except (TypeError, ValueError):
        work_seconds = 0.0
    return BreakStatus(
        work_remaining_seconds=max(0, int(int(work_minutes) * 60 - work_seconds))
    )
