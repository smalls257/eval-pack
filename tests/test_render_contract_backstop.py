# tests/test_render_contract_backstop.py
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import render_html  # noqa: E402
import config  # noqa: E402


class TestContractBackstop(unittest.TestCase):
    def test_validate_pack_includes_contract_gaps(self):
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d)
            base = dict(json.loads(json.dumps(config.DEFAULTS)))
            base["retrospectiveQuestions"] = ["Q1?"]
            (pack / "eval-config.json").write_text(json.dumps(base), encoding="utf-8")
            (pack / "transcript.jsonl").write_text(json.dumps(
                {"type": "assistant", "message": {"content": "hi"}}) + "\n", encoding="utf-8")
            (pack / "metrics.json").write_text(json.dumps({"turnCount": 1}), encoding="utf-8")
            (pack / "analysis.json").write_text(json.dumps({"title": "t"}), encoding="utf-8")
            gaps = render_html.validate_pack(pack)
            self.assertTrue(any("retrospectiveAnswers" in g for g in gaps))


if __name__ == "__main__":
    unittest.main()
