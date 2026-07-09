# tests/test_render_contract_backstop.py
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
PLUGIN_ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))
import validate_contracts  # noqa: E402
import config  # noqa: E402


def _make_pack(out_dir, sid, questions=None, answers=None):
    pack = Path(out_dir) / sid
    pack.mkdir(parents=True)
    base = dict(json.loads(json.dumps(config.DEFAULTS)))
    if questions:
        base["retrospectiveQuestions"] = questions
    (pack / "eval-config.json").write_text(json.dumps(base), encoding="utf-8")
    (pack / "transcript.jsonl").write_text(json.dumps(
        {"type": "assistant", "message": {"content": "hi"}}) + "\n", encoding="utf-8")
    (pack / "metrics.json").write_text(json.dumps({"turnCount": 1}), encoding="utf-8")
    analysis = {"title": "t"}
    if answers:
        analysis["retrospectiveAnswers"] = answers
    (pack / "analysis.json").write_text(json.dumps(analysis), encoding="utf-8")
    (pack / "patterns.json").write_text(json.dumps({"flags": []}), encoding="utf-8")
    (pack / "test-results.json").write_text(json.dumps({"verdict": "none"}), encoding="utf-8")
    return pack


def _render(out_dir, sid, pack):
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "render_html.py"), str(out_dir), sid,
         str(PLUGIN_ROOT), str(pack / "transcript.jsonl"), "--branch", sid],
        capture_output=True, text=True)


class TestContractBackstop(unittest.TestCase):
    def test_violation_refuses_but_preserves_pack(self):
        with tempfile.TemporaryDirectory() as out:
            pack = _make_pack(out, "gate", questions=["Q1?"])
            r = _render(out, "gate", pack)
            self.assertEqual(r.returncode, 1)
            self.assertIn("CONTRACT:", r.stderr)
            self.assertIn("retrospectiveAnswers", r.stderr)
            # the evidence survives — no rmtree on contract gaps
            self.assertTrue((pack / "analysis.json").is_file())
            self.assertTrue((pack / "eval-config.json").is_file())

    def test_conforming_pack_renders(self):
        with tempfile.TemporaryDirectory() as out:
            pack = _make_pack(out, "ok", questions=["Q1?"],
                              answers=[{"question": "Q1?", "answer": "a"}])
            self.assertEqual(validate_contracts.collect_gaps(pack), [])
            r = _render(out, "ok", pack)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(list(Path(out).glob("*.zip")))  # pack actually shipped


if __name__ == "__main__":
    unittest.main()
