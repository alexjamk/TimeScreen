"""Read-only update checks against the official GitHub release endpoint."""

import json
import urllib.request
from dataclasses import dataclass
from typing import Callable, Optional
from urllib.parse import urlparse

from app_info import APP_VERSION, REPOSITORY_URL


LATEST_RELEASE_API = "https://api.github.com/repos/alexjamk/TimeScreen/releases/latest"


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    page_url: str
    is_newer: bool


def version_tuple(value: str) -> tuple[int, ...]:
    cleaned = value.strip().lower()
    if cleaned.startswith("v"):
        cleaned = cleaned[1:]
    parts = cleaned.split(".")
    if not 2 <= len(parts) <= 4 or not all(part.isdigit() for part in parts):
        raise ValueError("Некорректный номер версии")
    return tuple(int(part) for part in parts)


def is_newer_version(candidate: str, current: str = APP_VERSION) -> bool:
    candidate_parts = version_tuple(candidate)
    current_parts = version_tuple(current)
    size = max(len(candidate_parts), len(current_parts))
    return candidate_parts + (0,) * (size - len(candidate_parts)) > current_parts + (0,) * (size - len(current_parts))


def _trusted_release_url(value: str) -> str:
    parsed = urlparse(value)
    expected_path = urlparse(REPOSITORY_URL).path.rstrip("/") + "/releases/"
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com" or not parsed.path.startswith(expected_path):
        raise ValueError("GitHub вернул недопустимую ссылку на релиз")
    return value


def fetch_latest_release(
    timeout: int = 8,
    urlopen: Optional[Callable] = None,
) -> ReleaseInfo:
    opener = urlopen or (lambda request, value: urllib.request.urlopen(request, timeout=value))  # nosec B310
    request = urllib.request.Request(
        LATEST_RELEASE_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"TimeScreenControl/{APP_VERSION}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with opener(request, timeout) as response:
        if hasattr(response, "geturl"):
            final = urlparse(response.geturl())
            if final.scheme != "https" or final.netloc.lower() != "api.github.com":
                raise ValueError("Сервер обновлений выполнил недопустимое перенаправление")
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Некорректный ответ сервера обновлений")
    version = str(payload.get("tag_name", "")).strip()
    if version.lower().startswith("v"):
        version = version[1:]
    page_url = _trusted_release_url(str(payload.get("html_url", "")))
    version_tuple(version)
    return ReleaseInfo(version=version, page_url=page_url, is_newer=is_newer_version(version))

