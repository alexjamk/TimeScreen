"""Consistent enumeration of visible, enabled local Windows accounts."""

import json
import os
import subprocess
from typing import List
from pathlib import Path


EXCLUDED_USERS = {
    "administrator", "guest", "defaultaccount", "wdagutilityaccount",
    "defaultapppool", "iusr", "iwam", "system",
    "администратор", "гость", "система",
}


def _visible(names, current: str = "") -> List[str]:
    unique = {}
    for name in names:
        display = str(name).strip()
        normalized = display.casefold()
        if (display and normalized not in EXCLUDED_USERS
                and not normalized.startswith("codexsandbox")
                and not display.endswith("$")):
            unique.setdefault(normalized, display)
    return sorted(
        unique.values(),
        key=lambda name: (name.casefold() != current.casefold(), name.casefold()),
    )


def get_visible_windows_users() -> List[str]:
    """Return enabled normal local users, excluding built-in service accounts."""
    current = os.environ.get("USERNAME", "")
    names = []
    try:
        import win32net
        import win32netcon

        rows, _total, _resume = win32net.NetUserEnum(
            None, 1, win32netcon.FILTER_NORMAL_ACCOUNT
        )
        names = [
            row["name"] for row in rows
            if not int(row.get("flags", 0)) & win32netcon.UF_ACCOUNTDISABLE
        ]
    except Exception:
        try:
            command = (
                "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; "
                "Get-LocalUser | Where-Object { $_.Enabled -eq $true } | "
                "Select-Object -ExpandProperty Name | ConvertTo-Json"
            )
            result = subprocess.run(
                [str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"),
                 "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                capture_output=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode == 0 and result.stdout:
                parsed = json.loads(result.stdout.decode("utf-8-sig", errors="replace").strip())
                names = [parsed] if isinstance(parsed, str) else parsed
        except Exception:
            names = []

    if current and current.casefold() not in EXCLUDED_USERS:
        names.append(current)
    return _visible(names, current)
