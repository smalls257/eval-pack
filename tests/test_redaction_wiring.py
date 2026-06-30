# tests/test_redaction_wiring.py
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import render_html  # noqa: E402
import config  # noqa: E402

SECRET = "sk-SECRET12345"


def _write_transcript(path):
    line = {"type": "assistant", "timestamp": "2026-06-30T00:00:00Z",
            "message": {"role": "assistant",
                        "content": "here is my key " + SECRET + " ok"}}
    path.write_text(json.dumps(line) + "\n", encoding="utf-8")


class TestTranscriptHtmlRedaction(unittest.TestCase):
    def test_secret_masked_in_transcript_html(self):
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d)
            tpath = pack / "transcript.jsonl"
            _write_transcript(tpath)
            render_html.render_transcript_html(
                tpath, pack, pack / "screenshots", [r"sk-[A-Za-z0-9]+"]
            )
            html = (pack / "transcript.html").read_text(encoding="utf-8")
            self.assertNotIn(SECRET, html)
            self.assertIn("[REDACTED]", html)


class TestRawJsonlRedaction(unittest.TestCase):
    def test_secret_masked_in_raw_jsonl(self):
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d)
            _write_transcript(pack / "transcript.jsonl")
            render_html.redact_transcript_file(pack, [r"sk-[A-Za-z0-9]+"])
            raw = (pack / "transcript.jsonl").read_text(encoding="utf-8")
            self.assertNotIn(SECRET, raw)
            self.assertIn("[REDACTED]", raw)

    def test_no_rules_leaves_file_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d)
            _write_transcript(pack / "transcript.jsonl")
            before = (pack / "transcript.jsonl").read_text(encoding="utf-8")
            render_html.redact_transcript_file(pack, [])
            self.assertEqual((pack / "transcript.jsonl").read_text(encoding="utf-8"), before)


class TestInvalidRedactionRegex(unittest.TestCase):
    def test_bad_regex_flagged_by_validate(self):
        errs = config.validate({"redaction": ["("]})
        self.assertTrue(any("redaction" in e for e in errs))


if __name__ == "__main__":
    unittest.main()
