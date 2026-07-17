# tests/test_validate_contracts.py
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import validate_contracts  # noqa: E402
import config  # noqa: E402


def _run(cmd, cwd=None):
    out = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"{cmd} failed: {out.stderr}")
    return out.stdout


def _init_repo(path):
    path.mkdir(parents=True, exist_ok=True)
    _run(["git", "init", "-q"], cwd=str(path))
    _run(["git", "config", "user.email", "t@example.com"], cwd=str(path))
    _run(["git", "config", "user.name", "T"], cwd=str(path))
    _run(["git", "commit", "--allow-empty", "-q", "-m", "init"], cwd=str(path))
    return path


def _edit_entry(repo, filename):
    return {
        "type": "assistant",
        "cwd": str(repo),
        "message": {
            "content": [
                {"type": "tool_use", "name": "Edit",
                 "input": {"file_path": str(repo / filename)}},
            ]
        },
    }


def _read_entry(repo, filename):
    return {
        "type": "assistant",
        "cwd": str(repo),
        "message": {
            "content": [
                {"type": "tool_use", "name": "Read",
                 "input": {"file_path": str(repo / filename)}},
            ]
        },
    }


def _write_transcript(pack_dir, entries):
    t = Path(pack_dir) / "transcript.jsonl"
    t.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")
    return t


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
    """Coverage is re-derived from transcript.jsonl (ground truth) via discover_repos.discover,
    NOT from the skill-written discovered-repos.json — so a skill run that skipped discovery
    can't silently pass a multi-repo session as single-repo (Sensor: observed at render time)."""

    def _diffs(self, d, repos=None, skipped=None, errors=None):
        (Path(d) / "repo-diffs.json").write_text(json.dumps({
            "repos": repos or [], "skipped": skipped or [], "errors": errors or [],
        }), encoding="utf-8")

    def test_single_write_repo_no_gap(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _init_repo(Path(d) / "repo")
            (repo / "a.py").write_text("x = 1\n", encoding="utf-8")
            _write_transcript(d, [_edit_entry(repo, "a.py")])
            self.assertEqual(validate_contracts._repo_coverage_gaps(d), [])

    def test_two_write_repos_no_diffs_file_is_gap(self):
        with tempfile.TemporaryDirectory() as d:
            repo_a = _init_repo(Path(d) / "repo_a")
            repo_b = _init_repo(Path(d) / "repo_b")
            (repo_a / "a.py").write_text("x = 1\n", encoding="utf-8")
            (repo_b / "b.py").write_text("y = 2\n", encoding="utf-8")
            _write_transcript(d, [_edit_entry(repo_a, "a.py"), _edit_entry(repo_b, "b.py")])
            gaps = validate_contracts._repo_coverage_gaps(d)
            self.assertTrue(gaps)
            joined = " ".join(gaps)
            self.assertIn("repo-diffs.json", joined)
            self.assertIn(os.path.realpath(repo_a), joined)
            self.assertIn(os.path.realpath(repo_b), joined)

    def test_two_write_repos_all_accounted_no_gap(self):
        with tempfile.TemporaryDirectory() as d:
            repo_a = _init_repo(Path(d) / "repo_a")
            repo_b = _init_repo(Path(d) / "repo_b")
            (repo_a / "a.py").write_text("x = 1\n", encoding="utf-8")
            (repo_b / "b.py").write_text("y = 2\n", encoding="utf-8")
            _write_transcript(d, [_edit_entry(repo_a, "a.py"), _edit_entry(repo_b, "b.py")])
            self._diffs(d, repos=[{"repoRoot": os.path.realpath(repo_a)}],
                        skipped=[{"repoRoot": os.path.realpath(repo_b)}])
            self.assertEqual(validate_contracts._repo_coverage_gaps(d), [])

    def test_two_write_repos_one_unaccounted_is_gap(self):
        with tempfile.TemporaryDirectory() as d:
            repo_a = _init_repo(Path(d) / "repo_a")
            repo_b = _init_repo(Path(d) / "repo_b")
            (repo_a / "a.py").write_text("x = 1\n", encoding="utf-8")
            (repo_b / "b.py").write_text("y = 2\n", encoding="utf-8")
            _write_transcript(d, [_edit_entry(repo_a, "a.py"), _edit_entry(repo_b, "b.py")])
            self._diffs(d, repos=[{"repoRoot": os.path.realpath(repo_a)}])
            gaps = validate_contracts._repo_coverage_gaps(d)
            self.assertTrue(any(os.path.realpath(repo_b) in g for g in gaps))
            self.assertFalse(any(os.path.realpath(repo_a) in g for g in gaps))

    def test_read_only_repo_not_gated(self):
        with tempfile.TemporaryDirectory() as d:
            repo_a = _init_repo(Path(d) / "repo_a")
            repo_b = _init_repo(Path(d) / "repo_b")
            (repo_a / "a.py").write_text("x = 1\n", encoding="utf-8")
            (repo_b / "b.py").write_text("y = 2\n", encoding="utf-8")
            _write_transcript(d, [_edit_entry(repo_a, "a.py"), _read_entry(repo_b, "b.py")])
            # Only repo_a is write-touched; repo_b was merely read (e.g. a dependency
            # or cache repo) — this must NOT force multi-repo coverage.
            self.assertEqual(validate_contracts._repo_coverage_gaps(d), [])

    def test_errored_base_is_gap(self):
        with tempfile.TemporaryDirectory() as d:
            repo_a = _init_repo(Path(d) / "repo_a")
            repo_b = _init_repo(Path(d) / "repo_b")
            (repo_a / "a.py").write_text("x = 1\n", encoding="utf-8")
            (repo_b / "b.py").write_text("y = 2\n", encoding="utf-8")
            _write_transcript(d, [_edit_entry(repo_a, "a.py"), _edit_entry(repo_b, "b.py")])
            self._diffs(d, repos=[{"repoRoot": os.path.realpath(repo_a)}],
                        skipped=[{"repoRoot": os.path.realpath(repo_b)}],
                        errors=[{"repoRoot": os.path.realpath(repo_a), "error": "base ref not found"}])
            gaps = validate_contracts._repo_coverage_gaps(d)
            self.assertTrue(any(os.path.realpath(repo_a) in g and "base ref not found" in g
                                 for g in gaps))

    def test_no_transcript_no_gap(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(validate_contracts._repo_coverage_gaps(d), [])

    def test_unaccounted_repo_fails_collect_gaps(self):
        with tempfile.TemporaryDirectory() as d:
            _pack(d, analysis={"title": "t"})
            repo_a = _init_repo(Path(d) / "repo_a")
            repo_b = _init_repo(Path(d) / "repo_b")
            (repo_a / "a.py").write_text("x = 1\n", encoding="utf-8")
            (repo_b / "b.py").write_text("y = 2\n", encoding="utf-8")
            _write_transcript(d, [_edit_entry(repo_a, "a.py"), _edit_entry(repo_b, "b.py")])
            gaps = validate_contracts.collect_gaps(d)
            self.assertTrue(any(os.path.realpath(repo_a) in g or os.path.realpath(repo_b) in g
                                 for g in gaps))


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
