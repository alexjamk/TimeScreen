"""Tests for lock-screen background validation and storage."""

import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from gui.lock_background import install_background


class TestLockBackground(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.destination = self.root / "shared" / "lock_background.jpg"

    def tearDown(self):
        self.temp.cleanup()

    def test_png_is_reencoded_to_shared_jpeg(self):
        source = self.root / "picture.png"
        Image.new("RGB", (100, 60), "red").save(source)
        install_background(source, self.destination)
        with Image.open(self.destination) as stored:
            self.assertEqual(stored.format, "JPEG")
            self.assertEqual(stored.size, (100, 60))

    def test_invalid_file_does_not_replace_existing_background(self):
        source = self.root / "picture.png"
        Image.new("RGB", (20, 20), "blue").save(source)
        install_background(source, self.destination)
        original = self.destination.read_bytes()
        source.write_text("not an image", encoding="utf-8")
        with self.assertRaises(ValueError):
            install_background(source, self.destination)
        self.assertEqual(self.destination.read_bytes(), original)

    def test_oversize_source_is_rejected(self):
        source = self.root / "large.png"
        with source.open("wb") as stream:
            stream.truncate(20 * 1024 * 1024 + 1)
        with self.assertRaises(ValueError):
            install_background(source, self.destination)


if __name__ == "__main__":
    unittest.main()
