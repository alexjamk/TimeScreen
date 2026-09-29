"""Regression tests for system prompts displayed over the lock screen."""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from gui.lock_screen import LockScreen


class FakeWindow:
    def __init__(self):
        self.topmost = True
        self.lift_count = 0

    def attributes(self, name, value):
        if name == "-topmost":
            self.topmost = value

    def lift(self):
        self.lift_count += 1


class TestLockScreenSystemPrompts(unittest.TestCase):
    def make_lock(self):
        lock = LockScreen.__new__(LockScreen)
        lock.root = FakeWindow()
        lock.secondary_windows = [FakeWindow()]
        lock._system_prompt_active = False
        lock.status_label = Mock()
        return lock

    def test_system_prompt_temporarily_removes_topmost_from_every_monitor(self):
        lock = self.make_lock()

        lock._begin_system_prompt()
        self.assertTrue(lock._system_prompt_active)
        self.assertFalse(lock.root.topmost)
        self.assertFalse(lock.secondary_windows[0].topmost)

        lock._end_system_prompt()
        self.assertFalse(lock._system_prompt_active)
        self.assertTrue(lock.root.topmost)
        self.assertTrue(lock.secondary_windows[0].topmost)
        self.assertEqual(lock.root.lift_count, 1)

    def test_cancelled_power_confirmation_never_runs_command_and_restores_topmost(self):
        lock = self.make_lock()
        topmost_during_question = []

        def cancel_question(*_args, **_kwargs):
            topmost_during_question.append(lock.root.topmost)
            return False

        with patch("gui.lock_screen.messagebox.askyesno", side_effect=cancel_question), patch(
            "gui.lock_screen.subprocess.run"
        ) as run:
            self.assertFalse(lock._confirm_power_action("Restart?", ["shutdown", "/r"]))

        run.assert_not_called()
        self.assertEqual(topmost_during_question, [True])
        self.assertFalse(lock._system_prompt_active)
        self.assertTrue(lock.root.topmost)

    def test_power_command_runs_only_after_confirmation(self):
        lock = self.make_lock()
        completed = SimpleNamespace(returncode=0)
        with patch("gui.lock_screen.messagebox.askyesno", return_value=True), patch(
            "gui.lock_screen.subprocess.run", return_value=completed
        ) as run:
            self.assertTrue(lock._confirm_power_action("Restart?", ["shutdown", "/r"]))

        run.assert_called_once_with(["shutdown", "/r"], capture_output=True)
        self.assertTrue(lock.root.topmost)

    def test_cancelled_uac_restores_topmost(self):
        lock = self.make_lock()
        lock._is_current_windows_admin = Mock(return_value=False)
        lock._request_uac_grace = Mock(return_value=False)

        lock._windows_admin_unlock()

        self.assertFalse(lock._system_prompt_active)
        self.assertTrue(lock.root.topmost)


if __name__ == "__main__":
    unittest.main()
