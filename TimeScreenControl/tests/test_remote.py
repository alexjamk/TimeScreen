"""Tests for device identity, rotating codes and sync conflict handling."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from service.remote import RemoteSync


class TestRemoteSync(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "remote.json"
        self.remote = RemoteSync(self.path, "https://example.invalid/api.php")

    def tearDown(self):
        self.temp.cleanup()

    def test_pairing_code_is_six_digits_and_rotates(self):
        state = {"pairing_secret": "11" * 32}
        first = self.remote.pairing_code(state, 60)
        self.assertRegex(first, r"^\d{6}$")
        self.assertEqual(first, self.remote.pairing_code(state, 119))
        self.assertNotEqual(first, self.remote.pairing_code(state, 120))

    def test_enable_generates_persistent_device_credentials(self):
        with patch.object(self.remote, "register"):
            first = self.remote.enable("Домашний ПК")
            second = self.remote.enable("Домашний ПК")
        self.assertEqual(first["device_id"], second["device_id"])
        self.assertEqual(first["device_token"], second["device_token"])
        self.assertNotIn("device_token", self.remote.status())

    def test_settings_hash_is_order_independent(self):
        self.assertEqual(
            self.remote._settings_hash({"enabled": True, "intervals": []}),
            self.remote._settings_hash({"intervals": [], "enabled": True}),
        )


if __name__ == "__main__":
    unittest.main()
