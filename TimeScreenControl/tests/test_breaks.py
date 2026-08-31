"""Tests for persistent per-user recurring break accounting."""

import datetime
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from service.breaks import BreakTracker, get_break_cycle_status


class TestBreakTracker(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.path = Path(self.tmpdir.name) / "break_state.json"
        self.start = datetime.datetime(2026, 8, 31, 8, 0)
        self.tracker = BreakTracker(
            state_path=self.path,
            wall_clock=lambda: self.start,
            monotonic_clock=lambda: 0.0,
        )
        self.tracker.MAX_COUNTED_GAP_SECONDS = 4000

    def tearDown(self):
        self.tmpdir.cleanup()

    def update(self, seconds, eligible=True, username="Child", now=None):
        return self.tracker.update(
            username=username,
            enabled=True,
            eligible_for_work=eligible,
            work_minutes=60,
            break_minutes=10,
            now=now or self.start + datetime.timedelta(seconds=seconds),
            monotonic_now=float(seconds),
        )

    def test_notifications_and_break_are_triggered_at_cycle_boundaries(self):
        self.update(0)
        status = self.update(3000)
        self.assertEqual(status.work_remaining_seconds, 600)
        self.assertEqual(status.notifications, [10])
        self.assertEqual(self.update(3300).notifications, [5])
        self.assertEqual(self.update(3540).notifications, [1])
        status = self.update(3600)
        self.assertTrue(status.in_break)
        self.assertEqual(status.break_remaining_seconds, 600)

    def test_ineligible_time_and_user_switch_are_not_counted(self):
        self.update(0)
        self.update(5, eligible=False)
        status = self.update(10)
        self.assertEqual(status.work_remaining_seconds, 3595)
        self.update(15, username="Administrator")
        status = self.update(20)
        self.assertEqual(status.work_remaining_seconds, 3595)

    def test_long_gap_such_as_sleep_is_not_counted(self):
        self.tracker.MAX_COUNTED_GAP_SECONDS = 15
        self.update(0)
        status = self.update(8 * 3600)
        self.assertEqual(status.work_remaining_seconds, 3600)

    def test_break_persists_and_expiry_starts_new_cycle(self):
        self.update(0)
        self.update(3600)
        persisted = get_break_cycle_status(
            "child", 60, 10, self.start + datetime.timedelta(seconds=3660), self.path
        )
        self.assertTrue(persisted.in_break)
        self.assertEqual(persisted.break_remaining_seconds, 540)

        status = self.update(
            4201,
            now=self.start + datetime.timedelta(seconds=4201),
        )
        self.assertFalse(status.in_break)
        self.assertEqual(status.work_remaining_seconds, 3600)

    def test_policy_change_resets_progress(self):
        self.update(0)
        self.update(1800)
        status = self.tracker.update(
            username="Child",
            enabled=True,
            eligible_for_work=True,
            work_minutes=90,
            break_minutes=15,
            now=self.start + datetime.timedelta(seconds=1805),
            monotonic_now=1805,
        )
        self.assertEqual(status.work_remaining_seconds, 90 * 60)


if __name__ == "__main__":
    unittest.main()
