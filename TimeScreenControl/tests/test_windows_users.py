"""Tests for the shared visible Windows account filter."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from utils.windows_users import _visible


class TestWindowsUsers(unittest.TestCase):
    def test_system_disabled_style_names_are_hidden_consistently(self):
        users = _visible(
            ["Child", "Administrator", "Guest", "DefaultAccount", "svc$", "Parent", "child", "CodexSandboxOnline"],
            "Parent",
        )
        self.assertEqual(users, ["Parent", "Child"])


if __name__ == "__main__":
    unittest.main()
