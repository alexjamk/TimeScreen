"""
TimeScreen Control - Unit Tests for ConfigManager
"""

import unittest
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config.manager import ConfigManager
from config.security import hash_password, verify_password, compute_hash


class TestSecurity(unittest.TestCase):
    """Test security functions."""
    
    def test_hash_password_bcrypt(self):
        """Test password hashing produces valid hash."""
        password = "test123"
        hashed = hash_password(password)
        
        # Hash should be non-empty and different from password
        self.assertIsNotNone(hashed)
        self.assertNotEqual(hashed, password)
        self.assertTrue(len(hashed) > 10)
    
    def test_verify_password_correct(self):
        """Test verifying correct password."""
        password = "securepass456"
        hashed = hash_password(password)
        
        self.assertTrue(verify_password(password, hashed))
    
    def test_verify_password_incorrect(self):
        """Test verifying wrong password."""
        password = "correctpass"
        hashed = hash_password(password)
        
        self.assertFalse(verify_password("wrongpass", hashed))
    
    def test_compute_hash_consistency(self):
        """Test hash computation is consistent."""
        data = {"key": "value", "number": 42}
        
        hash1 = compute_hash(data)
        hash2 = compute_hash(data)
        
        self.assertEqual(hash1, hash2)
    
    def test_compute_hash_changes_with_data(self):
        """Test hash changes when data changes."""
        data1 = {"key": "value1"}
        data2 = {"key": "value2"}
        
        hash1 = compute_hash(data1)
        hash2 = compute_hash(data2)
        
        self.assertNotEqual(hash1, hash2)


class TestConfigManager(unittest.TestCase):
    """Test ConfigManager functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Use a test config path (in memory simulation)
        self.cfg = ConfigManager(read_only=False)
    
    def tearDown(self):
        """Clean up after tests."""
        # Reset config to defaults
        if hasattr(self.cfg, 'config'):
            self.cfg.config = ConfigManager.DEFAULT_CONFIG.copy()
    
    def test_initial_config_has_defaults(self):
        """Test that initial config has default values."""
        self.assertIn("password_hash", self.cfg.config)
        self.assertIn("intervals", self.cfg.config)
        self.assertIn("enabled", self.cfg.config)
        self.assertIn("controlled_users", self.cfg.config)
    
    def test_has_password_false_initially(self):
        """Test has_password returns False initially."""
        self.assertFalse(self.cfg.has_password())
    
    def test_set_password_success(self):
        """Test setting a password."""
        result = self.cfg.set_password("testpass123")
        
        # Note: save() might fail in test environment without proper directories
        # but password should be set in memory
        self.assertTrue(self.cfg.has_password())
    
    def test_set_password_too_short(self):
        """Test setting too short password fails."""
        result = self.cfg.set_password("abc")  # Less than 4 chars
        
        self.assertFalse(result)
        self.assertFalse(self.cfg.has_password())
    
    def test_get_intervals_empty_initially(self):
        """Test intervals are empty initially."""
        intervals = self.cfg.get_intervals()
        
        self.assertIsInstance(intervals, list)
        self.assertEqual(len(intervals), 0)
    
    def test_add_interval_success(self):
        """Test adding a valid interval."""
        result = self.cfg.add_interval("08:00", "20:00", [0, 1, 2, 3, 4])
        
        intervals = self.cfg.get_intervals()
        self.assertEqual(len(intervals), 1)
        self.assertEqual(intervals[0]["start"], "08:00")
        self.assertEqual(intervals[0]["end"], "20:00")
        self.assertEqual(intervals[0]["days"], [0, 1, 2, 3, 4])
    
    def test_add_interval_invalid_time(self):
        """Test adding interval with invalid time fails."""
        result = self.cfg.add_interval("25:00", "20:00", [0])
        
        self.assertFalse(result)
    
    def test_add_interval_invalid_days(self):
        """Test adding interval with invalid days fails."""
        result = self.cfg.add_interval("08:00", "20:00", [])
        
        self.assertFalse(result)
    
    def test_remove_interval(self):
        """Test removing an interval."""
        self.cfg.add_interval("08:00", "20:00", [0])
        self.cfg.add_interval("10:00", "18:00", [1])
        
        result = self.cfg.remove_interval(0)
        
        intervals = self.cfg.get_intervals()
        self.assertEqual(len(intervals), 1)
        self.assertEqual(intervals[0]["start"], "10:00")
    
    def test_clear_intervals(self):
        """Test clearing all intervals."""
        self.cfg.add_interval("08:00", "20:00", [0])
        self.cfg.add_interval("10:00", "18:00", [1])
        
        result = self.cfg.clear_intervals()
        
        intervals = self.cfg.get_intervals()
        self.assertEqual(len(intervals), 0)
    
    def test_controlled_users_default_all(self):
        """Test that empty controlled users means all users."""
        users = self.cfg.get_controlled_users()
        
        self.assertIsInstance(users, list)
        self.assertEqual(len(users), 0)
        
        # Empty list means control everyone
        self.assertTrue(self.cfg.is_controlled_user("anyuser"))
    
    def test_set_controlled_users(self):
        """Test setting controlled users."""
        result = self.cfg.set_controlled_users(["user1", "user2"])
        
        users = self.cfg.get_controlled_users()
        self.assertEqual(len(users), 2)
        self.assertIn("user1", users)
        self.assertIn("user2", users)
    
    def test_is_enabled_default_true(self):
        """Test protection is enabled by default."""
        self.assertTrue(self.cfg.is_enabled())
    
    def test_set_enabled(self):
        """Test enabling/disabling protection."""
        self.cfg.set_enabled(False)
        self.assertFalse(self.cfg.is_enabled())
        
        self.cfg.set_enabled(True)
        self.assertTrue(self.cfg.is_enabled())
    
    def test_timer_position_default(self):
        """Test default timer position."""
        pos = self.cfg.get_timer_position()
        
        self.assertEqual(pos, (100, 100))
    
    def test_set_timer_position(self):
        """Test setting timer position."""
        result = self.cfg.set_timer_position(200, 300)
        
        pos = self.cfg.get_timer_position()
        self.assertEqual(pos, (200, 300))


class TestTimeChecking(unittest.TestCase):
    """Test time checking logic."""
    
    def setUp(self):
        self.cfg = ConfigManager(read_only=False)
        self.cfg.clear_intervals()
    
    def test_no_intervals_allows_all(self):
        """Test that no intervals means always allowed."""
        self.assertTrue(self.cfg.is_allowed_time())
    
    def test_protection_disabled_allows_all(self):
        """Test that disabled protection means always allowed."""
        self.cfg.add_interval("08:00", "20:00", list(range(7)))
        self.cfg.set_enabled(False)
        
        self.assertTrue(self.cfg.is_allowed_time())
    
    def test_current_time_in_interval(self):
        """Test time checking within interval."""
        # This test would need mocking of current time
        # For now, just verify the method exists and returns boolean
        result = self.cfg.is_allowed_time()
        self.assertIsInstance(result, bool)
    
    def test_get_next_event_no_intervals(self):
        """Test get_next_event with no intervals."""
        seconds, event_type = self.cfg.get_next_event()
        
        self.assertIsNone(seconds)
        self.assertIsNone(event_type)


if __name__ == "__main__":
    unittest.main()
