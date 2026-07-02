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


def _entry(etype, text):
    return {"type": etype, "message": {"content": [{"type": "text", "text": text}]}}


class TestConfigurableDetection(unittest.TestCase):
    def test_custom_done_pattern(self):
        entries = [_entry("assistant", "task fertig jetzt"), _entry("user", "nein, broken")]
        rx = detect_patterns.compile_patterns({"done": [r"(?i)fertig"],
                                               "correction": [r"(?i)(nein|broken)"],
                                               "retry": [r"(?i)nochmal"]})
        found = detect_patterns.detect_false_completions(entries, rx, window=1, trunc=120)
        self.assertEqual(len(found), 1)

    def test_window_extends_reach(self):
        entries = [_entry("assistant", "all done"),
                   _entry("assistant", "wrapping up"),
                   _entry("user", "no, still broken")]
        rx = detect_patterns.compile_patterns(detect_patterns.DEFAULT_PATTERNS)
        self.assertEqual(len(detect_patterns.detect_false_completions(entries, rx, window=1, trunc=120)), 0)
        self.assertEqual(len(detect_patterns.detect_false_completions(entries, rx, window=2, trunc=120)), 1)

    def test_trunc_len_applied(self):
        entries = [_entry("assistant", "done " + "x" * 300), _entry("user", "no, wrong")]
        rx = detect_patterns.compile_patterns(detect_patterns.DEFAULT_PATTERNS)
        found = detect_patterns.detect_false_completions(entries, rx, window=1, trunc=10)
        self.assertEqual(len(found[0]["agentClaim"]), 10)


if __name__ == "__main__":
    unittest.main()
