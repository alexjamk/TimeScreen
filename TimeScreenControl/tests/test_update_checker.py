"""Tests for safe update discovery without network access."""

import io
import json
import sys
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from utils.update_checker import fetch_latest_release, is_newer_version, version_tuple


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class TestUpdateChecker(unittest.TestCase):
    def test_semantic_version_comparison(self):
        self.assertTrue(is_newer_version("3.4", "3.3"))
        self.assertTrue(is_newer_version("v4.0.0", "3.9.9"))
        self.assertFalse(is_newer_version("3.3.0", "3.3"))
        self.assertFalse(is_newer_version("3.2.9", "3.3"))
        with self.assertRaises(ValueError):
            version_tuple("latest")

    def test_release_response_is_parsed(self):
        def opener(request, timeout):
            self.assertEqual(timeout, 8)
            self.assertIn("api.github.com", request.full_url)
            return FakeResponse(json.dumps({
                "tag_name": "4.0",
                "html_url": "https://github.com/alexjamk/TimeScreen/releases/tag/4.0",
            }).encode())

        release = fetch_latest_release(urlopen=opener)
        self.assertEqual(release.version, "4.0")
        self.assertTrue(release.is_newer)

    def test_untrusted_release_url_is_rejected(self):
        def opener(_request, _timeout):
            return FakeResponse(json.dumps({
                "tag_name": "99.0",
                "html_url": "https://example.invalid/update.exe",
            }).encode())

        with self.assertRaises(ValueError):
            fetch_latest_release(urlopen=opener)

    def test_standard_urlopen_receives_keyword_timeout(self):
        response = FakeResponse(json.dumps({
            "tag_name": "3.4",
            "html_url": "https://github.com/alexjamk/TimeScreen/releases/tag/3.4",
        }).encode())
        with patch("urllib.request.urlopen", return_value=response) as urlopen:
            fetch_latest_release(timeout=11)
        self.assertEqual(urlopen.call_args.kwargs, {"timeout": 11})


if __name__ == "__main__":
    unittest.main()

