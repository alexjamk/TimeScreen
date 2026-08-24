"""Service-level tests for active-session user scoping."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from service.daemon import TimeScreenService


class FakeConfig:
    def __init__(self, blocked_user):
        self.blocked_user = blocked_user
        self.checked_username = None

    def should_block_user(self, username):
        self.checked_username = username
        return username.casefold() == self.blocked_user.casefold()


class TestServiceUserScoping(unittest.TestCase):
    def make_service(self, username):
        service = TimeScreenService.__new__(TimeScreenService)
        service.lock_screens = {}
        service._clean_finished_processes = lambda: None
        service._get_active_identity = lambda: (7, username)
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
        config = FakeConfig("Child")
        with patch("service.daemon.ConfigManager", return_value=config):
            service._check_and_enforce()
        self.assertEqual(config.checked_username, "Administrator")
        self.assertEqual(service.actions, [("unlock", 7)])


if __name__ == "__main__":
    unittest.main()
