# tests/test_validate_contracts.py
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import validate_contracts  # noqa: E402
import config  # noqa: E402


def _pack(d, cfg_over=None, analysis=None, test_results=None):
    pack = Path(d)
    base = dict(json.loads(json.dumps(config.DEFAULTS)))
    base.update(cfg_over or {})
    (pack / "eval-config.json").write_text(json.dumps(base), encoding="utf-8")
    if analysis is not None:
        (pack / "analysis.json").write_text(json.dumps(analysis), encoding="utf-8")
    if test_results is not None:
        (pack / "test-results.json").write_text(json.dumps(test_results), encoding="utf-8")
    return pack


class TestFrictionContract(unittest.TestCase):
    def test_offlist_friction_type_is_gap(self):
        with tempfile.TemporaryDirectory() as d:
            _pack(d, {"frictionCategories": ["tooling", "docs"]},
                  analysis={"title": "t", "frictionLog": [{"friction": "x", "type": "vibes"}]})
            gaps = validate_contracts.collect_gaps(d)
            self.assertTrue(any("frictionLog" in g and "vibes" in g for g in gaps))

    def test_onlist_type_ok(self):
        with tempfile.TemporaryDirectory() as d:
            _pack(d, {"frictionCategories": ["tooling", "docs"]},
                  analysis={"title": "t", "frictionLog": [{"friction": "x", "type": "docs"}]})
            self.assertEqual(validate_contracts.collect_gaps(d), [])


class TestRetrospectiveContract(unittest.TestCase):
    def test_missing_answer_is_gap(self):
        with tempfile.TemporaryDirectory() as d:
            _pack(d, {"retrospectiveQuestions": ["Q1?", "Q2?"]},
                  analysis={"title": "t", "retrospectiveAnswers": [
                      {"question": "Q1?", "answer": "a"}]})
            gaps = validate_contracts.collect_gaps(d)
            self.assertTrue(any("Q2?" in g for g in gaps))

    def test_all_answered_ok(self):
        with tempfile.TemporaryDirectory() as d:
            _pack(d, {"retrospectiveQuestions": ["Q1?"]},
                  analysis={"title": "t", "retrospectiveAnswers": [
                      {"question": "Q1?", "answer": "a"}]})
            self.assertEqual(validate_contracts.collect_gaps(d), [])


class TestRubricContract(unittest.TestCase):
    def test_missing_or_unknown_band_is_gap(self):
        with tempfile.TemporaryDirectory() as d:
            _pack(d, {"rubric": {"high": "ship it", "low": "block"}},
                  analysis={"title": "t"})
            self.assertTrue(any("rubricApplied" in g for g in validate_contracts.collect_gaps(d)))
        with tempfile.TemporaryDirectory() as d:
            _pack(d, {"rubric": {"high": "ship it"}},
                  analysis={"title": "t", "rubricApplied": {"band": "banana", "why": "w"}})
            self.assertTrue(any("banana" in g for g in validate_contracts.collect_gaps(d)))

    def test_valid_band_ok(self):
        with tempfile.TemporaryDirectory() as d:
            _pack(d, {"rubric": {"high": "ship it"}},
                  analysis={"title": "t", "rubricApplied": {"band": "high", "why": "w"}})
            self.assertEqual(validate_contracts.collect_gaps(d), [])


class TestTestCommandContract(unittest.TestCase):
    def test_commands_must_match_and_verdict_consistent(self):
        with tempfile.TemporaryDirectory() as d:
            _pack(d, {"testCommands": ["cmd-a", "cmd-b"]},
                  analysis={"title": "t"},
                  test_results={"verdict": "pass",
                                "commands": [{"command": "cmd-a", "exitCode": 0},
                                             {"command": "cmd-b", "exitCode": 1}]})
            gaps = validate_contracts.collect_gaps(d)
            self.assertTrue(any("verdict" in g for g in gaps))  # exit 1 but verdict pass
        with tempfile.TemporaryDirectory() as d:
            _pack(d, {"testCommands": ["cmd-a"]},
                  analysis={"title": "t"},
                  test_results={"verdict": "fail", "commands": [{"command": "other", "exitCode": 1}]})
            gaps = validate_contracts.collect_gaps(d)
            self.assertTrue(any("cmd-a" in g for g in gaps))  # configured command not proven run

    def test_conforming_run_ok(self):
        with tempfile.TemporaryDirectory() as d:
            _pack(d, {"testCommands": ["cmd-a"]},
                  analysis={"title": "t"},
                  test_results={"verdict": "pass", "commands": [{"command": "cmd-a", "exitCode": 0}]})
            self.assertEqual(validate_contracts.collect_gaps(d), [])


class TestDisabledAnalysisSkips(unittest.TestCase):
    def test_disabled_stub_skips_analysis_contracts(self):
        with tempfile.TemporaryDirectory() as d:
            _pack(d, {"retrospectiveQuestions": ["Q1?"], "rubric": {"h": "x"}},
                  analysis={"title": "disabled", "disabled": True})
            self.assertEqual(validate_contracts.collect_gaps(d), [])


if __name__ == "__main__":
    unittest.main()
