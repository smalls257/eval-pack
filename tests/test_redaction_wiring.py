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
RULES = [r"sk-[A-Za-z0-9]+"]


class TestRedactPackCoversAllArtifacts(unittest.TestCase):
    """The no-leak invariant: a planted secret must be masked in EVERY emitted text
    artifact, not just the transcript — the bug the branch audit caught."""

    def _plant(self, pack):
        (pack / "transcript.html").write_text(f"<pre>{SECRET}</pre>", encoding="utf-8")
        (pack / "transcript.jsonl").write_text(json.dumps({"x": SECRET}) + "\n", encoding="utf-8")
        (pack / "analysis.json").write_text(json.dumps({"quote": SECRET}), encoding="utf-8")
        (pack / "tools.json").write_text(json.dumps({"skills": [{"args": SECRET}]}), encoding="utf-8")
        (pack / "data.json").write_text(json.dumps({"analysis": {"quote": SECRET}}), encoding="utf-8")
        (pack / "index.html").write_text(f"<script>var d={{'k':'{SECRET}'}}</script>", encoding="utf-8")

    def test_secret_masked_across_all_text_artifacts(self):
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d)
            self._plant(pack)
            render_html.redact_pack(pack, RULES)
            for name in ("transcript.html", "transcript.jsonl", "analysis.json",
                         "tools.json", "data.json", "index.html"):
                txt = (pack / name).read_text(encoding="utf-8")
                self.assertNotIn(SECRET, txt, name)
                self.assertIn("[REDACTED]", txt, name)

    def test_no_rules_leaves_files_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d)
            (pack / "analysis.json").write_text(json.dumps({"q": SECRET}), encoding="utf-8")
            render_html.redact_pack(pack, [])
            self.assertIn(SECRET, (pack / "analysis.json").read_text(encoding="utf-8"))


class TestOpenableDirGuard(unittest.TestCase):
    def test_within_repo_detected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.assertTrue(render_html._is_within(root / "public" / "packs", root))
            self.assertTrue(render_html._is_within(root, root))

    def test_outside_repo_allowed(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as other:
            self.assertFalse(render_html._is_within(Path(other) / "packs", Path(root)))


class TestInvalidRedactionRegex(unittest.TestCase):
    def test_bad_regex_flagged_by_validate(self):
        errs = config.validate({"redaction": ["("]})
        self.assertTrue(any("redaction" in e for e in errs))


if __name__ == "__main__":
    unittest.main()
