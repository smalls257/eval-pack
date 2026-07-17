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


class TestCliContract(unittest.TestCase):
    def test_exit_codes_and_stderr_prefix(self):
        import subprocess
        with tempfile.TemporaryDirectory() as d:
            _pack(d, {"rubric": {"high": "x"}}, analysis={"title": "t"})
            r = subprocess.run([sys.executable, str(SCRIPTS / "validate_contracts.py"), d],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 1)
            self.assertTrue(any(line.startswith("CONTRACT: ") for line in r.stderr.splitlines()))
        with tempfile.TemporaryDirectory() as d:
            _pack(d, {}, analysis={"title": "t"})
            r = subprocess.run([sys.executable, str(SCRIPTS / "validate_contracts.py"), d],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0)


class TestRepoCoverageContract(unittest.TestCase):
    def _discovered(self, d, repos):
        (Path(d) / "discovered-repos.json").write_text(json.dumps(repos), encoding="utf-8")

    def _diffs(self, d, repos=None, skipped=None, errors=None):
        (Path(d) / "repo-diffs.json").write_text(json.dumps({
            "repos": repos or [], "skipped": skipped or [], "errors": errors or [],
        }), encoding="utf-8")

    def test_no_discovered_repos_file_no_gap(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(validate_contracts._repo_coverage_gaps(d), [])

    def test_all_discovered_accounted_no_gap(self):
        with tempfile.TemporaryDirectory() as d:
            self._discovered(d, [
                {"repoRoot": "/repo/a", "branch": "main"},
                {"repoRoot": "/repo/b", "branch": "main"},
            ])
            self._diffs(d, repos=[{"repoRoot": "/repo/a"}], skipped=[{"repoRoot": "/repo/b"}])
            self.assertEqual(validate_contracts._repo_coverage_gaps(d), [])

    def test_unaccounted_repo_is_gap(self):
        with tempfile.TemporaryDirectory() as d:
            self._discovered(d, [
                {"repoRoot": "/repo/a", "branch": "main"},
                {"repoRoot": "/repo/b", "branch": "feature-x"},
            ])
            self._diffs(d, repos=[{"repoRoot": "/repo/a"}])
            gaps = validate_contracts._repo_coverage_gaps(d)
            self.assertTrue(any("/repo/b" in g and "feature-x" in g for g in gaps))

    def test_errored_base_is_gap(self):
        with tempfile.TemporaryDirectory() as d:
            self._discovered(d, [{"repoRoot": "/repo/a", "branch": "main"}])
            self._diffs(d, repos=[{"repoRoot": "/repo/a"}],
                        errors=[{"repoRoot": "/repo/a", "error": "base ref not found"}])
            gaps = validate_contracts._repo_coverage_gaps(d)
            self.assertTrue(any("/repo/a" in g and "base ref not found" in g for g in gaps))

    def test_discovered_but_no_diffs_file_is_gap(self):
        with tempfile.TemporaryDirectory() as d:
            self._discovered(d, [{"repoRoot": "/repo/a", "branch": "main"}])
            gaps = validate_contracts._repo_coverage_gaps(d)
            self.assertTrue(any("repo-diffs.json" in g for g in gaps))

    def test_symlink_var_path_variant_still_matches(self):
        import os
        with tempfile.TemporaryDirectory() as real_d:
            link = Path(real_d) / "link"
            target = Path(real_d) / "target"
            target.mkdir()
            os.symlink(target, link)
            # discovered uses the canonical (symlink-resolved) path; the selection
            # echoed the symlinked form — same repo, different string.
            canonical = os.path.realpath(target)
            symlinked = str(link)
            self.assertNotEqual(canonical, symlinked)
            with tempfile.TemporaryDirectory() as d:
                self._discovered(d, [{"repoRoot": canonical, "branch": "main"}])
                self._diffs(d, repos=[{"repoRoot": symlinked}])
                self.assertEqual(validate_contracts._repo_coverage_gaps(d), [])

    def test_trailing_slash_variant_matches(self):
        with tempfile.TemporaryDirectory() as d:
            self._discovered(d, [{"repoRoot": "/a/repo", "branch": "main"}])
            self._diffs(d, repos=[{"repoRoot": "/a/repo/"}])
            self.assertEqual(validate_contracts._repo_coverage_gaps(d), [])

    def test_empty_discovered_list_is_noop(self):
        with tempfile.TemporaryDirectory() as d:
            self._discovered(d, [])
            self.assertEqual(validate_contracts._repo_coverage_gaps(d), [])

    def test_genuinely_unaccounted_still_gaps(self):
        with tempfile.TemporaryDirectory() as d:
            self._discovered(d, [
                {"repoRoot": "/a/repo", "branch": "main"},
                {"repoRoot": "/totally/different/repo", "branch": "feature-x"},
            ])
            self._diffs(d, repos=[{"repoRoot": "/a/repo"}])
            gaps = validate_contracts._repo_coverage_gaps(d)
            self.assertTrue(any("/totally/different/repo" in g for g in gaps))

    def test_unaccounted_repo_fails_collect_gaps(self):
        with tempfile.TemporaryDirectory() as d:
            _pack(d, analysis={"title": "t"})
            self._discovered(d, [
                {"repoRoot": "/repo/a", "branch": "main"},
                {"repoRoot": "/repo/b", "branch": "feature-x"},
            ])
            self._diffs(d, repos=[{"repoRoot": "/repo/a"}])
            gaps = validate_contracts.collect_gaps(d)
            self.assertTrue(any("/repo/b" in g for g in gaps))


class TestConfigReadGaps(unittest.TestCase):
    def test_malformed_config_is_a_gap(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "eval-config.json").write_text("{not json", encoding="utf-8")
            gaps = validate_contracts.collect_gaps(d)
            self.assertTrue(any("unparseable" in g for g in gaps))

    def test_missing_config_defaults_keep_friction_live(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "analysis.json").write_text(
                json.dumps({"title": "t", "frictionLog": [{"friction": "x", "type": "vibes"}]}),
                encoding="utf-8")
            gaps = validate_contracts.collect_gaps(d)
            self.assertTrue(any("vibes" in g for g in gaps))


if __name__ == "__main__":
    unittest.main()
