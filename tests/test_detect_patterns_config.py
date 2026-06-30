# tests/test_detect_patterns_config.py
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import detect_patterns  # noqa: E402


class TestScopeDriftThreshold(unittest.TestCase):
    def _metrics(self, d, files_changed):
        (Path(d) / "metrics.json").write_text(
            json.dumps({"filesChanged": files_changed}), encoding="utf-8"
        )

    def test_uses_supplied_threshold(self):
        with tempfile.TemporaryDirectory() as d:
            self._metrics(d, 6)
            self.assertTrue(detect_patterns.check_scope_drift(d, threshold=5))
            self.assertFalse(detect_patterns.check_scope_drift(d, threshold=10))


if __name__ == "__main__":
    unittest.main()
