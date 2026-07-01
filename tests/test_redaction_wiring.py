# tests/test_redaction_wiring.py
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import render_html  # noqa: E402
import redact  # noqa: E402
import config  # noqa: E402

SECRET = "sk-SECRET12345"
RULES = [r"sk-[A-Za-z0-9]+"]


class TestRedactValue(unittest.TestCase):
    def test_recurses_strings_only(self):
        obj = {"a": SECRET, "b": [SECRET, 1, {"c": SECRET}], "n": 5}
        out = redact.redact_value(obj, RULES)
        self.assertEqual(out, {"a": "[REDACTED]", "b": ["[REDACTED]", 1, {"c": "[REDACTED]"}], "n": 5})

    def test_no_rules_identity(self):
        self.assertEqual(redact.redact_value({"a": SECRET}, []), {"a": SECRET})


class TestRedactPackValueLevel(unittest.TestCase):
    def test_json_secret_masked_and_valid_json(self):
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d)
            (pack / "analysis.json").write_text(json.dumps({"quote": "key " + SECRET}), encoding="utf-8")
            (pack / "tools.json").write_text(json.dumps({"skills": [{"args": SECRET}]}), encoding="utf-8")
            (pack / "transcript.jsonl").write_text(json.dumps({"m": SECRET}) + "\n", encoding="utf-8")
            render_html.redact_pack(pack, RULES)
            for name in ("analysis.json", "tools.json", "transcript.jsonl"):
                txt = (pack / name).read_text(encoding="utf-8")
                self.assertNotIn(SECRET, txt, name)
                self.assertIn("[REDACTED]", txt, name)
                # still valid: whole file for .json, first line for .jsonl
                json.loads(txt if name.endswith(".json") else txt.splitlines()[0])

    def test_no_rules_leaves_files_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d)
            (pack / "analysis.json").write_text(json.dumps({"q": SECRET}), encoding="utf-8")
            render_html.redact_pack(pack, [])
            self.assertIn(SECRET, (pack / "analysis.json").read_text(encoding="utf-8"))


class TestEscapeProofRedaction(unittest.TestCase):
    """SC-SEC-04: a secret containing HTML/JSON special characters must still be masked —
    redaction happens before escaping, so a plaintext rule is not defeated by escaping."""

    def test_special_char_secret_masked_in_json(self):
        # secret with a quote — would serialize as tok\"q and survive a naive regex-on-file pass
        secret = 'tok"q<v>&z'
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d)
            (pack / "analysis.json").write_text(json.dumps({"quote": secret}), encoding="utf-8")
            render_html.redact_pack(pack, [r'tok"q<v>&z'])
            txt = (pack / "analysis.json").read_text(encoding="utf-8")
            self.assertNotIn("tok", txt)        # no fragment of the secret survives
            self.assertIn("[REDACTED]", txt)
            json.loads(txt)                      # valid JSON

    def test_special_char_secret_masked_in_transcript_html(self):
        secret = 'tok"q<v>&z'
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d)
            tpath = pack / "transcript.jsonl"
            line = {"type": "assistant", "timestamp": "2026-06-30T00:00:00Z",
                    "message": {"role": "assistant", "content": "here " + secret + " end"}}
            tpath.write_text(json.dumps(line) + "\n", encoding="utf-8")
            render_html.render_transcript_html(tpath, pack, pack / "screenshots", [r'tok"q<v>&z'])
            html = (pack / "transcript.html").read_text(encoding="utf-8")
            self.assertNotIn("tok", html)
            self.assertIn("[REDACTED]", html)


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
