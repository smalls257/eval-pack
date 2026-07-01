# tests/test_assemble_lenses.py
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import assemble_lenses  # noqa: E402


def _pack(d, core=None, rule="min", lenses=None):
    pack = Path(d)
    if core is not None:
        (pack / "analysis.json").write_text(
            json.dumps({"highlights": {"confidencePercent": core}}), encoding="utf-8")
    (pack / "eval-config.json").write_text(json.dumps({"verdictAggregation": rule}), encoding="utf-8")
    ldir = pack / "lenses"
    ldir.mkdir(exist_ok=True)
    for name, obj in (lenses or {}).items():
        (ldir / (name + ".json")).write_text(json.dumps(obj), encoding="utf-8")
    return pack


class TestAssemble(unittest.TestCase):
    def test_scorer_feeds_verdict_via_rule(self):
        with tempfile.TemporaryDirectory() as d:
            _pack(d, core=80, rule="min", lenses={
                "cov": {"role": "scorer", "score": 61, "rationale": "low"},
            })
            out = assemble_lenses.assemble(d)
            self.assertEqual(out["coreScore"], 80)
            self.assertEqual(out["finalScore"], 61)  # min(80, 61)
            self.assertEqual(len(out["scorers"]), 1)

    def test_contributor_does_not_affect_score(self):
        with tempfile.TemporaryDirectory() as d:
            _pack(d, core=80, rule="min", lenses={
                "sec": {"role": "contributor", "title": "Security", "findings": ["ok"]},
            })
            out = assemble_lenses.assemble(d)
            self.assertEqual(len(out["contributors"]), 1)
            self.assertNotIn("finalScore", out)  # no scorers -> verdict untouched

    def test_non_numeric_scorer_is_failure_not_dropped(self):
        with tempfile.TemporaryDirectory() as d:
            _pack(d, core=80, rule="min", lenses={
                "bad": {"role": "scorer", "score": "high", "rationale": "x"},
            })
            out = assemble_lenses.assemble(d)
            self.assertEqual(out["scorers"], [])
            self.assertTrue(any(f.get("skill") == "bad" for f in out["failures"]))

    def test_malformed_lens_file_quarantined(self):
        with tempfile.TemporaryDirectory() as d:
            pack = _pack(d, core=80, rule="min", lenses={})
            (pack / "lenses" / "broken.json").write_text("{not json", encoding="utf-8")
            out = assemble_lenses.assemble(d)
            self.assertTrue(any(f.get("skill") == "broken" for f in out["failures"]))

    def test_no_lenses_no_finalscore(self):
        with tempfile.TemporaryDirectory() as d:
            _pack(d, core=80, rule="min", lenses={})
            out = assemble_lenses.assemble(d)
            self.assertEqual(out["scorers"], [])
            self.assertEqual(out["contributors"], [])


if __name__ == "__main__":
    unittest.main()
