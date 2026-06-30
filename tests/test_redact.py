# tests/test_redact.py
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import redact  # noqa: E402


class TestRedact(unittest.TestCase):
    def test_no_rules_is_unchanged(self):
        self.assertEqual(redact.redact("hello sk-ABC123", []), "hello sk-ABC123")

    def test_single_pattern_masked(self):
        out = redact.redact("token sk-ABC123 end", [r"sk-[A-Za-z0-9]+"])
        self.assertEqual(out, "token [REDACTED] end")

    def test_multiple_patterns(self):
        out = redact.redact(
            "user a@b.com key sk-XYZ",
            [r"[\w.]+@[\w.]+", r"sk-[A-Za-z0-9]+"],
        )
        self.assertEqual(out, "user [REDACTED] key [REDACTED]")

    def test_multiple_occurrences_all_masked(self):
        out = redact.redact("sk-1 sk-2 sk-3", [r"sk-\d"])
        self.assertEqual(out, "[REDACTED] [REDACTED] [REDACTED]")

    def test_mark_is_exported(self):
        self.assertEqual(redact.REDACTION_MARK, "[REDACTED]")


if __name__ == "__main__":
    unittest.main()
