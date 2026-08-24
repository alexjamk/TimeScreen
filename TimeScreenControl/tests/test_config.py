"""Unit tests for security, persistence, schedules and user scoping."""

import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import config.manager as manager_module
from config.manager import ConfigManager
from config.security import compute_hash, hash_password, verify_password


class TemporaryConfigMixin:
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        root = Path(self.tmpdir.name)
        self.originals = {
            "CONFIG_PATH": manager_module.CONFIG_PATH,
            "INTEGRITY_KEY_PATH": manager_module.INTEGRITY_KEY_PATH,
            "CONFIG_LOCK_PATH": manager_module.CONFIG_LOCK_PATH,
            "ensure_program_data_exists": manager_module.ensure_program_data_exists,
        }
        manager_module.CONFIG_PATH = root / "pc_config.json"
        manager_module.INTEGRITY_KEY_PATH = root / "integrity.key"
        manager_module.CONFIG_LOCK_PATH = root / "config.lock"
        manager_module.ensure_program_data_exists = lambda: root.mkdir(parents=True, exist_ok=True)
        self.cfg = ConfigManager(read_only=False)

    def tearDown(self):
        for name, value in self.originals.items():
            setattr(manager_module, name, value)
        self.tmpdir.cleanup()


class TestSecurity(unittest.TestCase):
    def test_password_hash_and_verification(self):
        hashed = hash_password("securepass456")
        self.assertNotEqual(hashed, "securepass456")
        self.assertTrue(verify_password("securepass456", hashed))
        self.assertFalse(verify_password("wrongpass", hashed))

    def test_hmac_depends_on_key_and_data(self):
        data = {"key": "value", "number": 42}
        self.assertEqual(compute_hash(data, b"a" * 32), compute_hash(data, b"a" * 32))
        self.assertNotEqual(compute_hash(data, b"a" * 32), compute_hash(data, b"b" * 32))
        self.assertNotEqual(compute_hash(data, b"a" * 32), compute_hash({"key": "other"}, b"a" * 32))


class TestConfigManager(TemporaryConfigMixin, unittest.TestCase):
    def test_initial_config_is_safe_and_disabled(self):
        self.assertFalse(self.cfg.is_enabled())
        self.assertFalse(self.cfg.has_password())
        self.assertEqual(self.cfg.get_intervals(), [])
        self.assertEqual(self.cfg.get_timer_position(), (100, 100))

    def test_password_requires_four_characters(self):
        self.assertFalse(self.cfg.set_password("123"))
        self.assertTrue(self.cfg.set_password("4272"))
        self.assertTrue(self.cfg.verify_password("4272"))

    def test_interval_crud(self):
        self.assertTrue(self.cfg.add_interval("08:00", "20:00", [0, 1]))
        self.assertTrue(self.cfg.add_interval("10:00", "18:00", [2]))
        self.assertTrue(self.cfg.replace_interval(0, "09:00", "21:00", [0]))
        self.assertEqual(self.cfg.get_intervals()[0]["start"], "09:00")
        self.assertTrue(self.cfg.remove_interval(1))
        self.assertEqual(len(self.cfg.get_intervals()), 1)
        self.assertTrue(self.cfg.clear_intervals())
        self.assertEqual(self.cfg.get_intervals(), [])

    def test_invalid_intervals_are_rejected(self):
        self.assertFalse(self.cfg.add_interval("25:00", "20:00", [0]))
        self.assertFalse(self.cfg.add_interval("08:00", "20:00", []))
        self.assertFalse(self.cfg.add_interval("08:00", "08:00", [0]))

    def test_user_selection_is_case_and_domain_insensitive(self):
        self.assertTrue(self.cfg.set_controlled_users(["Child"]))
        self.assertTrue(self.cfg.is_controlled_user("child"))
        self.assertTrue(self.cfg.is_controlled_user(r"DESKTOP\CHILD"))
        self.assertFalse(self.cfg.is_controlled_user("Administrator"))

    def test_empty_user_list_means_no_users(self):
        self.assertFalse(self.cfg.is_controlled_user("any-user"))

    def test_field_updates_do_not_restore_stale_password(self):
        stale = ConfigManager(read_only=False)
        self.assertTrue(self.cfg.set_password("new-password"))
        self.assertTrue(stale.set_timer_position(200, 300))
        reloaded = ConfigManager(read_only=True)
        self.assertTrue(reloaded.verify_password("new-password"))
        self.assertEqual(reloaded.get_timer_position(), (200, 300))

    def test_malformed_config_fails_closed(self):
        self.assertTrue(self.cfg.set_enabled(True))
        manager_module.CONFIG_PATH.write_text("{broken", encoding="utf-8")
        broken = ConfigManager(read_only=True)
        self.assertTrue(broken.config.get("_tampered"))
        self.assertTrue(broken.is_controlled_user("any-user"))
        self.assertFalse(broken.is_allowed_time())

    def test_missing_signature_fails_closed_after_initialization(self):
        self.assertTrue(self.cfg.set_enabled(True))
        raw = json.loads(manager_module.CONFIG_PATH.read_text(encoding="utf-8"))
        raw.pop("_hash")
        manager_module.CONFIG_PATH.write_text(json.dumps(raw), encoding="utf-8")
        broken = ConfigManager(read_only=True)
        self.assertTrue(broken.config.get("_tampered"))
        self.assertFalse(broken.is_allowed_time())

    def test_read_only_manager_cannot_write(self):
        readonly = ConfigManager(read_only=True)
        self.assertFalse(readonly.set_enabled(True))


class TestTimeChecking(TemporaryConfigMixin, unittest.TestCase):
    MONDAY = datetime(2026, 8, 24)

    def enable_with(self, *intervals):
        self.assertTrue(self.cfg.set_enabled(True))
        for start, end, days in intervals:
            self.assertTrue(self.cfg.add_interval(start, end, days))

    def test_no_intervals_allows_all(self):
        self.assertTrue(self.cfg.set_enabled(True))
        self.assertTrue(self.cfg.is_allowed_time(self.MONDAY))
        self.assertEqual(self.cfg.get_next_event(self.MONDAY), (None, None))

    def test_overnight_uses_start_day(self):
        self.enable_with(("22:00", "08:00", [0]))
        self.assertTrue(self.cfg.is_allowed_time(datetime(2026, 8, 25, 1, 0)))
        self.assertFalse(self.cfg.is_allowed_time(datetime(2026, 8, 26, 1, 0)))

    def test_future_weekday_is_found(self):
        self.enable_with(("08:00", "10:00", [2]))
        seconds, event = self.cfg.get_next_event(datetime(2026, 8, 24, 7, 0))
        self.assertEqual(event, "unlock")
        self.assertEqual(seconds, 49 * 3600)

    def test_overlapping_intervals_report_union_end(self):
        self.enable_with(("08:00", "10:00", [0]), ("09:00", "12:00", [0]))
        seconds, event = self.cfg.get_next_event(datetime(2026, 8, 24, 9, 30))
        self.assertEqual((seconds, event), (2 * 3600 + 30 * 60, "lock"))

    def test_end_boundary_is_exclusive(self):
        self.enable_with(("08:00", "10:00", [0]))
        self.assertTrue(self.cfg.is_allowed_time(datetime(2026, 8, 24, 9, 59, 59)))
        self.assertFalse(self.cfg.is_allowed_time(datetime(2026, 8, 24, 10, 0)))

    def test_grace_returns_boolean_and_timer_event(self):
        self.assertTrue(self.cfg.set_grace())
        self.assertIs(type(self.cfg.is_allowed_time()), bool)
        seconds, event = self.cfg.get_next_event()
        self.assertEqual(event, "grace")
        self.assertGreater(seconds, 0)

    def test_only_selected_child_is_blocked(self):
        self.enable_with(("08:00", "09:00", [0]))
        self.assertTrue(self.cfg.set_controlled_users(["Child"]))
        forbidden_time = datetime(2026, 8, 24, 10, 0)
        self.assertTrue(self.cfg.should_block_user("Child", forbidden_time))
        self.assertTrue(self.cfg.should_block_user(r"FAMILY\child", forbidden_time))
        self.assertFalse(self.cfg.should_block_user("Administrator", forbidden_time))

    def test_disabled_protection_blocks_nobody(self):
        self.assertTrue(self.cfg.set_controlled_users(["Child"]))
        self.assertFalse(self.cfg.should_block_user("Child", self.MONDAY))


if __name__ == "__main__":
    unittest.main()
