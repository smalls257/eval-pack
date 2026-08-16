# tests/test_assemble_lenses.py
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import assemble_lenses  # noqa: E402


def _pack(d, core=None, rule="min", lenses=None, analysis_lenses=None):
    pack = Path(d)
    if core is not None:
        (pack / "analysis.json").write_text(
            json.dumps({"highlights": {"confidencePercent": core}}), encoding="utf-8")
    lenses = lenses or {}
    # A resolved pack config always lists its lenses (the orphan guard assembles only
    # configured skills), so register each written file unless the caller overrides.
    if analysis_lenses is None:
        analysis_lenses = [{"skill": name, "role": obj.get("role", "contributor")}
                           for name, obj in lenses.items()]
    (pack / "eval-config.json").write_text(
        json.dumps({"verdictAggregation": rule, "analysisLenses": analysis_lenses}),
        encoding="utf-8")
    ldir = pack / "lenses"
    ldir.mkdir(exist_ok=True)
    for name, obj in lenses.items():
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
            # A CONFIGURED lens whose file is malformed is quarantined as a failure (not an
            # orphan): broken is listed in analysisLenses, so the orphan guard keeps it.
            pack = _pack(d, core=80, rule="min", lenses={},
                         analysis_lenses=[{"skill": "broken", "role": "scorer"}])
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

    def test_orphan_lens_file_not_in_config_is_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d); (pack / "lenses").mkdir()
            (pack / "lenses" / "verification-rigor.json").write_text(
                json.dumps({"skill": "verification-rigor", "role": "scorer", "score": 90, "rationale": "ok"}),
                encoding="utf-8")
            (pack / "lenses" / "ghost.json").write_text(
                json.dumps({"skill": "ghost", "role": "contributor", "title": "Ghost", "findings": ["boo"]}),
                encoding="utf-8")
            (pack / "analysis.json").write_text(json.dumps({"highlights": {"confidencePercent": 88}}), encoding="utf-8")
            self._cfg(d, [{"skill": "verification-rigor", "role": "scorer"}])
            out = assemble_lenses.assemble(d)
            skills = {r["skill"] for r in out["contributors"] + out["scorers"] + out["failures"]}
            self.assertNotIn("ghost", skills)
            self.assertIn("verification-rigor", skills)

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

    def test_templatehtml_carried_onto_result_not_onto_failure(self):
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d)
            (pack / "lenses").mkdir()
            (pack / "lenses" / "perf.json").write_text(
                json.dumps({"skill": "perf", "role": "scorer", "score": 61, "rationale": "slow"}),
                encoding="utf-8")
            (pack / "analysis.json").write_text(
                json.dumps({"highlights": {"confidencePercent": 90}}), encoding="utf-8")
            self._cfg(d, [
                {"skill": "perf", "role": "scorer", "templateHtml": "<b>{{score}}</b>"},
                {"skill": "ghost-lens", "role": "scorer"},
            ])
            out = assemble_lenses.assemble(d)
            perf = next(s for s in out["scorers"] if s["skill"] == "perf")
            self.assertEqual(perf["templateHtml"], "<b>{{score}}</b>")
            ghost = next(f for f in out["failures"] if f["skill"] == "ghost-lens")
            self.assertNotIn("templateHtml", ghost)

    def test_lens_self_supplied_templatehtml_is_stripped(self):
        # A lens's lenses/<skill>.json is LLM-authored — the untrusted source this feature
        # defends against. If it self-declares templateHtml with no configured template,
        # that markup must NOT survive to be rendered as trusted (stored-XSS guard).
        # Provenance: templateHtml is resolve-embedded ONLY.
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d)
            (pack / "lenses").mkdir()
            (pack / "lenses" / "evil.json").write_text(
                json.dumps({"skill": "evil", "role": "scorer", "score": 50, "rationale": "x",
                            "templateHtml": "<img src=x onerror=alert(1)>"}),
                encoding="utf-8")
            (pack / "analysis.json").write_text(
                json.dumps({"highlights": {"confidencePercent": 90}}), encoding="utf-8")
            self._cfg(d, [{"skill": "evil", "role": "scorer"}])  # NO template configured
            out = assemble_lenses.assemble(d)
            evil = next(s for s in out["scorers"] if s["skill"] == "evil")
            self.assertNotIn("templateHtml", evil)

    def test_configured_template_still_attached_after_strip(self):
        # Positive guard: the pop-then-set order must not break the legit path — a lens WITH
        # a configured (resolve-embedded) template still gets exactly that markup attached.
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d)
            (pack / "lenses").mkdir()
            (pack / "lenses" / "perf.json").write_text(
                json.dumps({"skill": "perf", "role": "scorer", "score": 61, "rationale": "slow",
                            "templateHtml": "<img src=x onerror=alert(1)>"}),  # self-declared decoy
                encoding="utf-8")
            (pack / "analysis.json").write_text(
                json.dumps({"highlights": {"confidencePercent": 90}}), encoding="utf-8")
            self._cfg(d, [{"skill": "perf", "role": "scorer", "templateHtml": "<b>{{score}}</b>"}])
            out = assemble_lenses.assemble(d)
            perf = next(s for s in out["scorers"] if s["skill"] == "perf")
            # The confined config markup wins; the lens's self-declared decoy never survives.
            self.assertEqual(perf["templateHtml"], "<b>{{score}}</b>")

    def test_display_carried_from_config_not_from_lens(self):
        # display is presentation config — config-sourced only, same trust rule as templateHtml.
        # A lens's self-declared display must NOT survive; the configured one wins.
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d)
            (pack / "lenses").mkdir()
            (pack / "lenses" / "business-risk.json").write_text(
                json.dumps({"skill": "business-risk", "role": "contributor",
                            "level": "medium", "notes": "x", "display": "tab"}),  # self-declared decoy
                encoding="utf-8")
            (pack / "lenses" / "perf.json").write_text(
                json.dumps({"skill": "perf", "role": "scorer", "score": 61, "rationale": "slow"}),
                encoding="utf-8")
            (pack / "analysis.json").write_text(
                json.dumps({"highlights": {"confidencePercent": 90}}), encoding="utf-8")
            self._cfg(d, [
                {"skill": "business-risk", "role": "contributor", "display": "card"},
                {"skill": "perf", "role": "scorer"},  # no display configured
            ])
            out = assemble_lenses.assemble(d)
            biz = next(c for c in out["contributors"] if c["skill"] == "business-risk")
            self.assertEqual(biz["display"], "card")  # config wins over lens self-declaration
            perf = next(s for s in out["scorers"] if s["skill"] == "perf")
            self.assertNotIn("display", perf)  # no display configured -> none attached

    def test_display_both_survives_config_reattach(self):
        # The 'both' value (summary card + detail tab) rides the same config-sourced reattach
        # path as 'card'; pin it so the round-trip is asserted, not merely inferred.
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d)
            (pack / "lenses").mkdir()
            (pack / "lenses" / "business-risk.json").write_text(
                json.dumps({"skill": "business-risk", "role": "contributor",
                            "level": "high", "notes": "x", "display": "card"}),  # self-declared decoy
                encoding="utf-8")
            (pack / "analysis.json").write_text(
                json.dumps({"highlights": {"confidencePercent": 90}}), encoding="utf-8")
            self._cfg(d, [
                {"skill": "business-risk", "role": "contributor", "display": "both"},
            ])
            out = assemble_lenses.assemble(d)
            biz = next(c for c in out["contributors"] if c["skill"] == "business-risk")
            self.assertEqual(biz["display"], "both")  # configured 'both' wins over the 'card' decoy

    def test_first_party_lens_gets_locked_version(self):
        # 'review' has a lockfile entry (1.0.2); a first-party lens with no configured
        # version inherits the trusted locked value onto its result.
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d)
            (pack / "lenses").mkdir()
            (pack / "lenses" / "review.json").write_text(
                json.dumps({"skill": "review", "role": "contributor",
                            "title": "Review", "findings": ["ok"]}),
                encoding="utf-8")
            (pack / "analysis.json").write_text(
                json.dumps({"highlights": {"confidencePercent": 90}}), encoding="utf-8")
            self._cfg(d, [{"skill": "review", "role": "contributor"}])
            out = assemble_lenses.assemble(d)
            review = next(c for c in out["contributors"] if c["skill"] == "review")
            self.assertEqual(review["version"], "1.0.2")  # from the lockfile

    def test_config_version_overrides_lockfile(self):
        # A configured version pins/overrides the locked value for that skill.
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d)
            (pack / "lenses").mkdir()
            (pack / "lenses" / "review.json").write_text(
                json.dumps({"skill": "review", "role": "contributor",
                            "title": "Review", "findings": ["ok"]}),
                encoding="utf-8")
            (pack / "analysis.json").write_text(
                json.dumps({"highlights": {"confidencePercent": 90}}), encoding="utf-8")
            self._cfg(d, [{"skill": "review", "role": "contributor", "version": "2.5.0"}])
            out = assemble_lenses.assemble(d)
            review = next(c for c in out["contributors"] if c["skill"] == "review")
            self.assertEqual(review["version"], "2.5.0")  # config wins over lockfile 1.0.2

    def test_lens_self_declared_version_is_stripped(self):
        # A lens's lenses/<skill>.json is LLM-authored (untrusted). A version it
        # self-declares must be stripped and replaced by the trusted config/lockfile value.
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d)
            (pack / "lenses").mkdir()
            (pack / "lenses" / "review.json").write_text(
                json.dumps({"skill": "review", "role": "contributor",
                            "title": "Review", "findings": ["ok"],
                            "version": "9.9.9"}),  # self-declared decoy
                encoding="utf-8")
            (pack / "analysis.json").write_text(
                json.dumps({"highlights": {"confidencePercent": 90}}), encoding="utf-8")
            self._cfg(d, [{"skill": "review", "role": "contributor"}])
            out = assemble_lenses.assemble(d)
            review = next(c for c in out["contributors"] if c["skill"] == "review")
            self.assertEqual(review["version"], "1.0.2")  # trusted lockfile, not the decoy
            self.assertNotEqual(review["version"], "9.9.9")

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
