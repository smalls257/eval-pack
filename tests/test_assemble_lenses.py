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


class TestLensGates(unittest.TestCase):
    def _cfg(self, d, lenses, rule="min"):
        import config
        base = dict(json.loads(json.dumps(config.DEFAULTS)))
        base["analysisLenses"] = lenses
        base["verdictAggregation"] = rule
        (Path(d) / "eval-config.json").write_text(json.dumps(base), encoding="utf-8")

    def test_configured_but_missing_lens_is_failure(self):
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d)
            (pack / "lenses").mkdir()
            (pack / "analysis.json").write_text(
                json.dumps({"highlights": {"confidencePercent": 90}}), encoding="utf-8")
            self._cfg(d, [{"skill": "ghost-lens", "role": "scorer"}])
            out = assemble_lenses.assemble(d)
            self.assertTrue(any(f.get("skill") == "ghost-lens" and "no output" in f.get("error", "")
                                for f in out["failures"]))

    def test_failure_emits_red_flag_into_patterns(self):
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d)
            (pack / "lenses").mkdir()
            (pack / "analysis.json").write_text(
                json.dumps({"highlights": {"confidencePercent": 90}}), encoding="utf-8")
            (pack / "patterns.json").write_text(json.dumps({"flags": []}), encoding="utf-8")
            self._cfg(d, [{"skill": "ghost-lens", "role": "scorer"}])
            out = assemble_lenses.assemble(d)
            assemble_lenses.write_outputs(d, out)
            patterns = json.loads((pack / "patterns.json").read_text(encoding="utf-8"))
            self.assertTrue(any(f["id"] == "lensFailed" and f["level"] == "red"
                                and "ghost-lens" in f["label"] for f in patterns["flags"]))

    def test_low_finalscore_emits_amber_flag_with_math(self):
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d)
            (pack / "lenses").mkdir()
            (pack / "lenses" / "perf.json").write_text(
                json.dumps({"skill": "perf", "role": "scorer", "score": 61, "rationale": "slow"}),
                encoding="utf-8")
            (pack / "analysis.json").write_text(
                json.dumps({"highlights": {"confidencePercent": 90}}), encoding="utf-8")
            (pack / "patterns.json").write_text(json.dumps({"flags": []}), encoding="utf-8")
            self._cfg(d, [{"skill": "perf", "role": "scorer"}])
            out = assemble_lenses.assemble(d)
            assemble_lenses.write_outputs(d, out)
            patterns = json.loads((pack / "patterns.json").read_text(encoding="utf-8"))
            flag = next(f for f in patterns["flags"] if f["id"] == "lensVerdict")
            self.assertEqual(flag["level"], "amber")
            self.assertIn("61", flag["label"])
            self.assertIn("90", flag["label"])

    def test_no_lenses_configured_no_flags_added(self):
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d)
            (pack / "analysis.json").write_text(
                json.dumps({"highlights": {"confidencePercent": 90}}), encoding="utf-8")
            (pack / "patterns.json").write_text(json.dumps({"flags": []}), encoding="utf-8")
            self._cfg(d, [])
            out = assemble_lenses.assemble(d)
            assemble_lenses.write_outputs(d, out)
            patterns = json.loads((pack / "patterns.json").read_text(encoding="utf-8"))
            self.assertEqual(patterns["flags"], [])  # Airplane Test: zero lenses = untouched

    def test_corrupt_patterns_warns_loudly(self):
        import io, contextlib
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d)
            (pack / "lenses").mkdir()
            (pack / "analysis.json").write_text(
                json.dumps({"highlights": {"confidencePercent": 90}}), encoding="utf-8")
            (pack / "patterns.json").write_text("{not json", encoding="utf-8")
            self._cfg(d, [{"skill": "ghost-lens", "role": "scorer"}])
            out = assemble_lenses.assemble(d)
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                assemble_lenses.write_outputs(d, out)
            self.assertIn("patterns.json was unreadable", err.getvalue())

    def test_lensverdict_honors_flagseverities_lensfailed_does_not(self):
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d)
            (pack / "lenses").mkdir()
            (pack / "lenses" / "perf.json").write_text(
                json.dumps({"skill": "perf", "role": "scorer", "score": 10, "rationale": "r"}),
                encoding="utf-8")
            (pack / "analysis.json").write_text(
                json.dumps({"highlights": {"confidencePercent": 90}}), encoding="utf-8")
            (pack / "patterns.json").write_text(json.dumps({"flags": []}), encoding="utf-8")
            import config as _config
            base = dict(json.loads(json.dumps(_config.DEFAULTS)))
            base["analysisLenses"] = [{"skill": "perf", "role": "scorer"},
                                       {"skill": "ghost", "role": "scorer"}]
            base["verdictAggregation"] = "min"
            base["flagSeverities"] = {"lensVerdict": "off", "lensFailed": "off"}
            (pack / "eval-config.json").write_text(json.dumps(base), encoding="utf-8")
            out = assemble_lenses.assemble(d)
            assemble_lenses.write_outputs(d, out)
            patterns = json.loads((pack / "patterns.json").read_text(encoding="utf-8"))
            self.assertFalse(any(f["id"] == "lensVerdict" for f in patterns["flags"]))  # honored
            self.assertTrue(any(f["id"] == "lensFailed" for f in patterns["flags"]))    # NOT suppressible

    def test_write_outputs_idempotent_on_rerun(self):
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d)
            (pack / "lenses").mkdir()
            (pack / "analysis.json").write_text(
                json.dumps({"highlights": {"confidencePercent": 90}}), encoding="utf-8")
            (pack / "patterns.json").write_text(
                json.dumps({"flags": [{"id": "highRetry", "level": "amber",
                                        "label": "High retry count", "count": 7}]}),
                encoding="utf-8")
            self._cfg(d, [{"skill": "ghost-lens", "role": "scorer"}])
            out = assemble_lenses.assemble(d)
            assemble_lenses.write_outputs(d, out)
            assemble_lenses.write_outputs(d, out)  # re-run
            patterns = json.loads((pack / "patterns.json").read_text(encoding="utf-8"))
            self.assertEqual(sum(1 for f in patterns["flags"] if f["id"] == "lensFailed"), 1)
            retry = next(f for f in patterns["flags"] if f["id"] == "highRetry")
            self.assertEqual(retry["count"], 7)  # detect flags survive untouched


if __name__ == "__main__":
    unittest.main()
