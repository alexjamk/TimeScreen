"""Service-level tests for active-session user scoping."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from service.daemon import TimeScreenService
from service.breaks import BreakStatus


class FakeConfig:
    def __init__(self, blocked_user):
        self.blocked_user = blocked_user
        self.checked_username = None

    def should_block_user(self, username):
        self.checked_username = username
        return username.casefold() == self.blocked_user.casefold()

    def get_break_settings(self):
        return {"enabled": True, "break_minutes": 10, "work_minutes": 60}

    def is_enabled(self):
        return True

    def is_controlled_user(self, username):
        return username.casefold() == self.blocked_user.casefold()

    def is_in_grace(self):
        return False

    def is_allowed_time(self):
        return False


class FakeBreakTracker:
    def __init__(self, status=None):
        self.status = status or BreakStatus()
        self.calls = []

    def update(self, **kwargs):
        self.calls.append(kwargs)
        return self.status


class TestServiceUserScoping(unittest.TestCase):
    def make_service(self, username):
        service = TimeScreenService.__new__(TimeScreenService)
        service.lock_screens = {}
        service._clean_finished_processes = lambda: None
        service._get_active_identity = lambda: (7, username)
        service.break_tracker = FakeBreakTracker()
        service._show_break_notification = lambda session, minutes: service.actions.append(
            ("notify", session, minutes)
        )
        service.actions = []
        service._ensure_lock_screen = lambda session, user: service.actions.append(("lock", session, user))
        service._terminate_lock_screen = lambda session: service.actions.append(("unlock", session))
        return service

    def test_selected_child_session_is_locked(self):
        service = self.make_service("Child")
        config = FakeConfig("Child")
        with patch("service.daemon.ConfigManager", return_value=config):
            service._check_and_enforce()
        self.assertEqual(config.checked_username, "Child")
        self.assertEqual(service.actions, [("lock", 7, "Child")])

    def test_unselected_admin_session_is_not_locked(self):
        service = self.make_service("Administrator")
        service.break_tracker = FakeBreakTracker(
            BreakStatus(in_break=True, notifications=[10])
        )
        config = FakeConfig("Child")
        with patch("service.daemon.ConfigManager", return_value=config):
            service._check_and_enforce()
        self.assertEqual(config.checked_username, "Administrator")
        self.assertEqual(service.actions, [("unlock", 7)])

    def test_break_locks_only_selected_user_and_shows_notifications(self):
        service = self.make_service("Child")
        service.break_tracker = FakeBreakTracker(BreakStatus(in_break=True, notifications=[10]))
        config = FakeConfig("Nobody")
        config.is_controlled_user = lambda username: username.casefold() == "child"
        config.should_block_user = lambda username: False
        config.is_allowed_time = lambda: True
        with patch("service.daemon.ConfigManager", return_value=config):
            service._check_and_enforce()
        self.assertEqual(service.actions, [("notify", 7, 10), ("lock", 7, "Child")])


class FakeUnlockConfig:
    def __init__(self, expected_password="4272", save_ok=True):
        self.expected_password = expected_password
        self.save_ok = save_ok
        self.last_error = ""
        self.grace_was_set = False

    def verify_password(self, password):
        return password == self.expected_password

    def set_grace(self):
        self.grace_was_set = self.save_ok
        return self.save_ok


class TestServicePasswordUnlock(unittest.TestCase):
    def make_service(self):
        service = TimeScreenService.__new__(TimeScreenService)
        service._failed_unlocks = []
        return service

    def test_test_password_grants_grace(self):
        service = self.make_service()
        config = FakeUnlockConfig()
        with patch("service.daemon.ConfigManager", return_value=config):
            response = service._handle_unlock_request(
                {"command": "grant_grace", "password": "4272"}
            )
        self.assertEqual(response, {"ok": True})
        self.assertTrue(config.grace_was_set)

    def test_wrong_password_does_not_grant_grace(self):
        service = self.make_service()
        config = FakeUnlockConfig()
        with patch("service.daemon.ConfigManager", return_value=config), patch("service.daemon.time.sleep"):
            response = service._handle_unlock_request(
                {"command": "grant_grace", "password": "wrong"}
            )
        self.assertFalse(response["ok"])
        self.assertFalse(config.grace_was_set)


if __name__ == "__main__":
    unittest.main()
