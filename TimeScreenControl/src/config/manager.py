"""Central, fail-closed configuration management for TimeScreen Control."""

import datetime
import json
import os
import secrets
import tempfile
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

from .paths import CONFIG_LOCK_PATH, CONFIG_PATH, INTEGRITY_KEY_PATH, ensure_program_data_exists
from .security import compute_hash, hash_password, verify_password


class ConfigManager:
    """Single source of truth with validation, HMAC integrity and atomic writes."""

    DEFAULT_CONFIG = {
        "password_hash": None,
        "intervals": [],
        "enabled": False,
        "controlled_users": [],
        "show_timer": True,
        "timer_position": [100, 100],
        "grace_until": None,
        "_hash": None,
    }
    GRACE_MINUTES = 10

    def __init__(self, read_only: bool = False):
        self.read_only = read_only
        self.last_error = ""
        ensure_program_data_exists()
        self.config = self._load()

    @staticmethod
    def _tampered_config(reason: str) -> dict:
        return {
            "password_hash": None, "intervals": [], "enabled": True,
            "controlled_users": [], "show_timer": False,
            "timer_position": [100, 100], "grace_until": None,
            "_tampered": True, "_tamper_reason": reason,
        }

    @staticmethod
    def _read_integrity_key() -> Optional[bytes]:
        try:
            key = INTEGRITY_KEY_PATH.read_bytes()
            return key if len(key) >= 32 else None
        except OSError:
            return None

    @staticmethod
    def _get_or_create_integrity_key() -> bytes:
        key = ConfigManager._read_integrity_key()
        if key:
            return key
        INTEGRITY_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
        candidate = secrets.token_bytes(32)
        try:
            with open(INTEGRITY_KEY_PATH, "xb") as stream:
                stream.write(candidate)
            return candidate
        except FileExistsError:
            key = ConfigManager._read_integrity_key()
            if not key:
                raise RuntimeError("Файл ключа целостности повреждён")
            return key

    @staticmethod
    def _validate_config(raw: dict) -> bool:
        if not isinstance(raw.get("enabled", True), bool) or not isinstance(raw.get("show_timer", True), bool):
            return False
        if raw.get("password_hash") is not None and not isinstance(raw.get("password_hash"), str):
            return False
        if raw.get("grace_until") is not None and not isinstance(raw.get("grace_until"), str):
            return False
        users = raw.get("controlled_users", [])
        if not isinstance(users, list) or not all(isinstance(user, str) for user in users):
            return False
        pos = raw.get("timer_position", [100, 100])
        if not (isinstance(pos, (list, tuple)) and len(pos) == 2 and
                all(isinstance(value, int) and not isinstance(value, bool) for value in pos)):
            return False
        intervals = raw.get("intervals", [])
        if not isinstance(intervals, list):
            return False
        for interval in intervals:
            if not isinstance(interval, dict):
                return False
            try:
                start = datetime.datetime.strptime(interval["start"], "%H:%M").time()
                end = datetime.datetime.strptime(interval["end"], "%H:%M").time()
                days = interval["days"]
            except (KeyError, TypeError, ValueError):
                return False
            if start == end or not isinstance(days, list) or not days:
                return False
            if not all(isinstance(day, int) and not isinstance(day, bool) and 0 <= day <= 6 for day in days):
                return False
        return True

    def _load(self) -> dict:
        """Load configuration; malformed or unsigned established data fails closed."""
        key = self._read_integrity_key()
        if not CONFIG_PATH.exists():
            return self._tampered_config("Файл конфигурации отсутствует") if key else deepcopy(self.DEFAULT_CONFIG)
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8-sig") as stream:
                raw = json.load(stream)
            if not isinstance(raw, dict):
                return self._tampered_config("Корневой элемент конфигурации не является объектом")
            stored_hash = raw.pop("_hash", None)
            if key:
                if not stored_hash or not secrets.compare_digest(stored_hash, compute_hash(raw, key)):
                    return self._tampered_config("Подпись конфигурации отсутствует или неверна")
            elif stored_hash and not secrets.compare_digest(stored_hash, compute_hash(raw)):
                return self._tampered_config("Устаревшая контрольная сумма неверна")
            if not self._validate_config(raw):
                return self._tampered_config("Конфигурация не прошла проверку схемы")
            config = deepcopy(self.DEFAULT_CONFIG)
            config.update(raw)
            if config.get("password_hash") == "":
                config["password_hash"] = None
            config["timer_position"] = list(config["timer_position"])
            return config
        except Exception as exc:
            return self._tampered_config(f"Ошибка чтения конфигурации: {exc}")

    @contextmanager
    def _write_lock(self) -> Iterator[None]:
        CONFIG_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_LOCK_PATH, "a+b") as lock_stream:
            if os.name != "nt":
                yield
                return
            import msvcrt
            lock_stream.seek(0, os.SEEK_END)
            if lock_stream.tell() == 0:
                lock_stream.write(b"0")
                lock_stream.flush()
            lock_stream.seek(0)
            msvcrt.locking(lock_stream.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                lock_stream.seek(0)
                msvcrt.locking(lock_stream.fileno(), msvcrt.LK_UNLCK, 1)

    def _save_unlocked(self, data: dict) -> bool:
        if data.get("_tampered"):
            self.last_error = "Конфигурация повреждена или была изменена вручную"
            return False
        temp_path: Optional[Path] = None
        try:
            key = self._get_or_create_integrity_key()
            payload = deepcopy(data)
            payload.pop("_tampered", None)
            payload.pop("_tamper_reason", None)
            payload["_hash"] = compute_hash(payload, key)
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temp_name = tempfile.mkstemp(prefix="pc_config.", suffix=".tmp", dir=str(CONFIG_PATH.parent))
            temp_path = Path(temp_name)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, indent=2, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(str(temp_path), str(CONFIG_PATH))
            self.config = deepcopy(data)
            self.config["_hash"] = None
            return True
        except Exception as exc:
            self.last_error = str(exc)
            if temp_path:
                try:
                    temp_path.unlink()
                except OSError:
                    pass
            return False

    def save(self) -> bool:
        if self.read_only:
            self.last_error = "Конфигурация открыта только для чтения"
            return False
        with self._write_lock():
            return self._save_unlocked(self.config)

    def _mutate(self, change: Callable[[dict], bool]) -> bool:
        if self.read_only:
            self.last_error = "Конфигурация открыта только для чтения"
            return False
        with self._write_lock():
            current = self._load()
            if current.get("_tampered"):
                self.config = current
                self.last_error = current.get("_tamper_reason", "Конфигурация повреждена")
                return False
            if not change(current):
                return False
            return self._save_unlocked(current)

    def has_password(self) -> bool:
        return bool(self.config.get("password_hash"))

    def set_password(self, password: str) -> bool:
        if len(password) < 8:
            self.last_error = "Пароль должен содержать не менее 8 символов"
            return False
        hashed = hash_password(password)
        return self._mutate(lambda data: data.update(password_hash=hashed) is None)

    def verify_password(self, password: str) -> bool:
        if self.config.get("_tampered"):
            return False
        stored_hash = self.config.get("password_hash")
        return bool(stored_hash) and verify_password(password, stored_hash)

    def get_intervals(self) -> List[Dict[str, Any]]:
        return deepcopy(self.config.get("intervals", []))

    def add_interval(self, start: str, end: str, days: List[int]) -> bool:
        try:
            start_time = datetime.datetime.strptime(start, "%H:%M").time()
            end_time = datetime.datetime.strptime(end, "%H:%M").time()
        except (TypeError, ValueError):
            self.last_error = "Неверный формат времени"
            return False
        if start_time == end_time:
            self.last_error = "Начало и конец интервала не должны совпадать"
            return False
        if not days or not all(isinstance(day, int) and not isinstance(day, bool) and 0 <= day <= 6 for day in days):
            self.last_error = "Неверно заданы дни недели"
            return False
        interval = {"start": start, "end": end, "days": sorted(set(days))}
        return self._mutate(lambda data: data.setdefault("intervals", []).append(interval) is None)

    def replace_interval(self, index: int, start: str, end: str, days: List[int]) -> bool:
        try:
            start_time = datetime.datetime.strptime(start, "%H:%M").time()
            end_time = datetime.datetime.strptime(end, "%H:%M").time()
        except (TypeError, ValueError):
            self.last_error = "Неверный формат времени"
            return False
        if start_time == end_time or not days or not all(isinstance(day, int) and 0 <= day <= 6 for day in days):
            self.last_error = "Неверный интервал"
            return False

        def change(data: dict) -> bool:
            intervals = data.get("intervals", [])
            if not 0 <= index < len(intervals):
                self.last_error = "Интервал не найден"
                return False
            intervals[index] = {"start": start, "end": end, "days": sorted(set(days))}
            return True
        return self._mutate(change)

    def remove_interval(self, index: int) -> bool:
        def change(data: dict) -> bool:
            intervals = data.get("intervals", [])
            if not 0 <= index < len(intervals):
                self.last_error = "Интервал не найден"
                return False
            intervals.pop(index)
            return True
        return self._mutate(change)

    def clear_intervals(self) -> bool:
        return self._mutate(lambda data: data.update(intervals=[]) is None)

    @staticmethod
    def normalize_username(username: str) -> str:
        value = (username or "").strip().replace("/", "\\")
        return value.rsplit("\\", 1)[-1].casefold()

    def get_controlled_users(self) -> List[str]:
        return list(self.config.get("controlled_users", []))

    def set_controlled_users(self, users: List[str]) -> bool:
        cleaned, seen = [], set()
        for user in users:
            display = user.strip()
            normalized = self.normalize_username(display)
            if display and normalized not in seen:
                cleaned.append(display)
                seen.add(normalized)
        return self._mutate(lambda data: data.update(controlled_users=cleaned) is None)

    def is_controlled_user(self, username: Optional[str] = None) -> bool:
        current = os.environ.get("USERNAME", "") if username is None else username
        if self.config.get("_tampered"):
            return True
        controlled = self.config.get("controlled_users", [])
        if not controlled:
            return False
        normalized = self.normalize_username(current)
        return bool(normalized) and normalized in {self.normalize_username(user) for user in controlled}

    def is_enabled(self) -> bool:
        return bool(self.config.get("enabled", False))

    def set_enabled(self, state: bool) -> bool:
        return self._mutate(lambda data: data.update(enabled=bool(state)) is None)

    def show_timer(self) -> bool:
        return bool(self.config.get("show_timer", True))

    def set_show_timer(self, show: bool) -> bool:
        return self._mutate(lambda data: data.update(show_timer=bool(show)) is None)

    def get_timer_position(self) -> Tuple[int, int]:
        pos = self.config.get("timer_position", [100, 100])
        return int(pos[0]), int(pos[1])

    def set_timer_position(self, x: int, y: int) -> bool:
        return self._mutate(lambda data: data.update(timer_position=[int(x), int(y)]) is None)

    def set_grace(self) -> bool:
        until = datetime.datetime.now() + datetime.timedelta(minutes=self.GRACE_MINUTES)
        return self._mutate(lambda data: data.update(grace_until=until.isoformat()) is None)

    def get_grace_remaining_seconds(self, now: Optional[datetime.datetime] = None) -> Optional[int]:
        timestamp = self.config.get("grace_until")
        if not timestamp:
            return None
        try:
            until = datetime.datetime.fromisoformat(timestamp)
            remaining = int((until - (now or datetime.datetime.now())).total_seconds())
            return remaining if remaining > 0 else None
        except (TypeError, ValueError):
            return None

    def is_in_grace(self, now: Optional[datetime.datetime] = None) -> bool:
        return self.get_grace_remaining_seconds(now) is not None

    def clear_grace(self) -> bool:
        return self._mutate(lambda data: data.update(grace_until=None) is None)

    def _iter_windows(self, reference: datetime.datetime, days_forward: int = 8) -> Iterator[Tuple[datetime.datetime, datetime.datetime]]:
        for offset in range(-1, days_forward + 1):
            date = reference.date() + datetime.timedelta(days=offset)
            for interval in self.config.get("intervals", []):
                if date.weekday() not in interval["days"]:
                    continue
                start_time = datetime.datetime.strptime(interval["start"], "%H:%M").time()
                end_time = datetime.datetime.strptime(interval["end"], "%H:%M").time()
                start = datetime.datetime.combine(date, start_time)
                end = datetime.datetime.combine(date, end_time)
                if end_time < start_time:
                    end += datetime.timedelta(days=1)
                yield start, end

    def is_allowed_time(self, now: Optional[datetime.datetime] = None) -> bool:
        if self.config.get("_tampered"):
            return False
        if not self.is_enabled():
            return True
        current = now or datetime.datetime.now()
        if self.is_in_grace(current):
            return True
        if not self.config.get("intervals"):
            return True
        return any(start <= current < end for start, end in self._iter_windows(current, 1))

    def should_block_user(self, username: str, now: Optional[datetime.datetime] = None) -> bool:
        """Return the complete enforcement decision for one explicit Windows user."""
        return (
            self.is_enabled()
            and self.is_controlled_user(username)
            and not self.is_in_grace(now)
            and not self.is_allowed_time(now)
        )

    def get_next_event(self, now: Optional[datetime.datetime] = None) -> Tuple[Optional[int], Optional[str]]:
        current = now or datetime.datetime.now()
        grace_seconds = self.get_grace_remaining_seconds(current)
        if grace_seconds is not None:
            return grace_seconds, "grace"
        if self.config.get("_tampered"):
            return None, "blocked_no_schedule"
        if not self.is_enabled() or not self.config.get("intervals"):
            return None, None
        allowed_now = self.is_allowed_time(current)
        boundaries = sorted({point for window in self._iter_windows(current, 8) for point in window if point > current})
        for boundary in boundaries:
            after = boundary + datetime.timedelta(microseconds=1)
            if self.is_allowed_time(after) != allowed_now:
                seconds = max(0, int((boundary - current).total_seconds()))
                return seconds, "lock" if allowed_now else "unlock"
        return (None, None) if allowed_now else (None, "blocked_no_schedule")
