"""Outbound-only secure synchronization with the TimeScreen Family web app."""

import hashlib
import hmac
import json
import os
import platform
import secrets
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator

from config.manager import ConfigManager
from config.paths import REMOTE_LOCK_PATH, REMOTE_STATE_PATH
from app_info import APP_VERSION


DEFAULT_API_URL = "https://time.k-alex.ru/api.php"


class RemoteSync:
    def __init__(self, state_path: Path = REMOTE_STATE_PATH, api_url: str = DEFAULT_API_URL):
        self.state_path = state_path
        self.lock_path = REMOTE_LOCK_PATH if state_path == REMOTE_STATE_PATH else state_path.with_suffix(".lock")
        self.api_url = api_url

    @staticmethod
    def _protect_secret_file(path: Path) -> None:
        """Allow only SYSTEM and administrators to read device credentials."""
        if os.name != "nt":
            path.chmod(0o600)
            return
        result = subprocess.run(
            [
                "icacls.exe", str(path), "/inheritance:r", "/grant:r",
                "*S-1-5-18:F", "*S-1-5-32-544:F",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0:
            raise OSError("Не удалось защитить учётные данные удалённого управления")

    def _load(self) -> dict:
        try:
            if self.state_path.exists():
                self._protect_secret_file(self.state_path)
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
            return state if isinstance(state, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    def _save(self, state: dict) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix="remote_state.", suffix=".tmp", dir=str(self.state_path.parent))
        try:
            self._protect_secret_file(Path(name))
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(state, stream, ensure_ascii=False, indent=2)
                stream.flush(); os.fsync(stream.fileno())
            os.replace(name, self.state_path)
        finally:
            try:
                os.unlink(name)
            except OSError:
                pass

    @contextmanager
    def _state_lock(self) -> Iterator[None]:
        """Serialize GUI and service updates to the shared device credentials."""
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.lock_path, "a+b") as lock_stream:
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

    def _mutate(self, update: Callable[[dict], None]) -> dict:
        with self._state_lock():
            state = self._load()
            update(state)
            self._save(state)
            return state

    def enable(self, device_name: str) -> dict:
        def update(state: dict) -> None:
            state.update({
                "enabled": True,
                "device_id": state.get("device_id") or str(uuid.uuid4()),
                "device_token": state.get("device_token") or secrets.token_urlsafe(32),
                "pairing_secret": state.get("pairing_secret") or secrets.token_hex(32),
                "device_name": (device_name or socket.gethostname())[:100],
                "known_revision": int(state.get("known_revision", 0)),
            })

        state = self._mutate(update)
        self.register(state)
        return state

    def disable(self) -> None:
        self._mutate(lambda state: state.update({"enabled": False}))

    @staticmethod
    def pairing_code(state: dict, timestamp: float | None = None) -> str:
        step = int((timestamp if timestamp is not None else time.time()) // 60)
        secret = bytes.fromhex(state["pairing_secret"])
        digest = hmac.new(secret, step.to_bytes(8, "big"), hashlib.sha256).digest()
        return f"{int.from_bytes(digest[-4:], 'big') % 1_000_000:06d}"

    @staticmethod
    def _settings_hash(settings: dict) -> str:
        raw = json.dumps(settings, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def _request(self, action: str, payload: dict, state: dict, authenticated: bool = True) -> dict:
        headers = {"Content-Type": "application/json", "User-Agent": f"TimeScreenControl/{APP_VERSION}"}
        if authenticated:
            headers["Authorization"] = f"Bearer {state['device_id']}.{state['device_token']}"
        request = urllib.request.Request(
            f"{self.api_url}?action={action}",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers=headers, method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=12) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, ValueError) as exc:
            raise RuntimeError("Сервер удалённого управления недоступен") from exc
        if not data.get("ok"):
            raise RuntimeError(data.get("error", "Ошибка удалённого управления"))
        return data

    def register(self, state: dict | None = None) -> None:
        state = state or self._load()
        self._request("device-register", {
            "device_id": state["device_id"], "token": state["device_token"],
            "name": state.get("device_name") or socket.gethostname(),
            "platform": f"{platform.system()} {platform.release()}",
        }, state, authenticated=False)

    def status(self) -> dict:
        state = self._load()
        result = {"enabled": bool(state.get("enabled")), "paired": bool(state.get("paired")), "device_name": state.get("device_name", socket.gethostname()), "last_success": state.get("last_success"), "last_error": state.get("last_error", "")}
        if result["enabled"] and state.get("pairing_secret"):
            result["code"] = self.pairing_code(state)
            result["seconds_remaining"] = 60 - int(time.time()) % 60
        return result

    @staticmethod
    def available_users() -> list[str]:
        try:
            import win32net
            rows, _total, _resume = win32net.NetUserEnum(None, 0, 2)
            return sorted({row["name"] for row in rows if row.get("name") and not row["name"].endswith("$")}, key=str.casefold)
        except Exception:
            return [os.environ.get("USERNAME", "")] if os.environ.get("USERNAME") else []

    def sync_once(self) -> None:
        state = self._load()
        if not state.get("enabled"):
            return
        try:
            self.register(state)
            code = self.pairing_code(state)
            pair = self._request("device-pair-code", {"code": code}, state)
            cfg = ConfigManager(read_only=False)
            settings = cfg.export_remote_settings()
            current_hash = self._settings_hash(settings)
            response = self._request("device-sync", {
                "known_revision": int(state.get("known_revision", 0)),
                "local_dirty": current_hash != state.get("last_config_hash"),
                "config": settings, "available_users": self.available_users(),
            }, state)
            remote = response.get("config")
            if remote is not None and self._settings_hash(remote) != current_hash:
                if not cfg.apply_remote_settings(remote):
                    raise RuntimeError(cfg.last_error or "Не удалось применить настройки")
                settings = remote
            acknowledged = []
            for command in response.get("commands", []):
                if command.get("type") == "grant-time" and cfg.set_grace_minutes(command.get("payload", {}).get("minutes")):
                    acknowledged.append(int(command["id"]))
            if acknowledged:
                self._request("device-ack", {"command_ids": acknowledged}, state)
            self._mutate(lambda latest: latest.update({
                "paired": bool(response.get("paired") or pair.get("paired")),
                "known_revision": int(response.get("revision", 0)),
                "last_config_hash": self._settings_hash(settings),
                "last_success": int(time.time()),
                "last_error": "",
            }))
        except Exception as exc:
            self._mutate(lambda latest: latest.update({"last_error": str(exc)}))
