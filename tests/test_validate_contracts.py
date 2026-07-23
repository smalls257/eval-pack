# tests/test_validate_contracts.py
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import validate_contracts  # noqa: E402
import config  # noqa: E402
from discover_repos import canon_root  # noqa: E402
# canon_root: the SAME canonicalization validate_contracts._canon_root delegates
# to, so assertions detect a Windows-only (separator/case) mismatch that a raw
# os.path.realpath() comparison here would paper over.


def _norm_slashes(s):
    """Fold path separators + case so a canonicalized path matches inside a gap message.

    Gap messages embed git's --show-toplevel output verbatim; on Windows that's
    the LONG name with FORWARD slashes, whereas canon_root() (which the expected
    side is passed through, to resolve the 8.3 short/long mismatch) emits native
    BACK slashes. This is a pure lexical fold — separators to '/', case-folded —
    with NO filesystem access, so it's safe to apply to an arbitrary sentence
    (the whole message), not just a path. The expected side is canon_root()'d
    FIRST (short->long + realpath) and then folded here; the message side is only
    folded here, because it already carries git's canonical long form.
    """
    return s.replace("\\", "/").casefold()


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


def _write_friction_lens(pack_dir, entries):
    lens_dir = Path(pack_dir) / "lenses"
    lens_dir.mkdir(parents=True, exist_ok=True)
    (lens_dir / "friction.json").write_text(json.dumps({
        "skill": "friction", "role": "contributor", "title": "Friction Log",
        "entries": entries,
    }), encoding="utf-8")


class TestFrictionContract(unittest.TestCase):
    """The friction taxonomy gate reads lenses/friction.json (the friction lens's own
    output), NOT analysis.json — the dimension was extracted into a default-on
    contributor lens (lens-decomposition Task 3); the deterministic gate moved with it."""

    def test_offlist_friction_type_is_gap(self):
        with tempfile.TemporaryDirectory() as d:
            _pack(d, {"frictionCategories": ["tooling", "docs"]}, analysis={"title": "t"})
            _write_friction_lens(d, [{"friction": "x", "impact": "y", "type": "vibes"}])
            gaps = validate_contracts.collect_gaps(d)
            self.assertTrue(any("friction entry type" in g and "vibes" in g for g in gaps))

    def test_onlist_type_ok(self):
        with tempfile.TemporaryDirectory() as d:
            _pack(d, {"frictionCategories": ["tooling", "docs"]}, analysis={"title": "t"})
            _write_friction_lens(d, [{"friction": "x", "impact": "y", "type": "docs"}])
            self.assertEqual(validate_contracts.collect_gaps(d), [])

    def test_absent_friction_lens_is_not_a_gap(self):
        """No lenses/friction.json (e.g. the lens is disabled, or Step 4's gate run happens
        before Step 4.7 assembles lenses) must NOT be gated here — a configured-but-missing
        lens is already the non-suppressible 'lensFailed' red flag from assemble_lenses.py;
        double-gating the same absence would be a confusing duplicate signal."""
        with tempfile.TemporaryDirectory() as d:
            _pack(d, {"frictionCategories": ["tooling", "docs"]}, analysis={"title": "t"})
            self.assertEqual(validate_contracts.collect_gaps(d), [])

    def test_render_time_gate_refuses_offlist_type(self):
        """Proof the relocated gate still deterministically blocks a bad friction type at the
        render-time collect_gaps call (render_html enforces this same call after lenses run)."""
        with tempfile.TemporaryDirectory() as d:
            _pack(d, {"frictionCategories": ["tooling", "docs"]}, analysis={"title": "t"})
            _write_friction_lens(d, [{"friction": "x", "impact": "y", "type": "not-a-real-category"}])
            gaps = validate_contracts.collect_gaps(d)
            self.assertTrue(gaps, "expected the render-time gate to refuse an off-taxonomy type")
            self.assertTrue(any("not-a-real-category" in g for g in gaps))

    def test_entry_missing_type_is_gap(self):
        with tempfile.TemporaryDirectory() as d:
            _pack(d, {"frictionCategories": ["tooling", "docs"]}, analysis={"title": "t"})
            _write_friction_lens(d, [{"friction": "x", "impact": "y"}])  # no type key
            gaps = validate_contracts.collect_gaps(d)
            self.assertTrue(any("friction entry type" in g for g in gaps))


class TestFrictionMalformedLens(unittest.TestCase):
    """lenses/friction.json is LLM-authored — the gate now reads it, so any shape it can
    emit (top-level list, non-list entries, non-dict entry, null entries) must yield a
    deterministic GAP or a clean no-op, never an uncaught exception. A crash here would be
    a Black Box: render_html's collect_gaps call has no try/except, so an AttributeError
    would die with a raw traceback and NO CONTRACT: line — the opposite of a clean gate."""

    def _write_raw_friction(self, pack_dir, payload_json):
        lens_dir = Path(pack_dir) / "lenses"
        lens_dir.mkdir(parents=True, exist_ok=True)
        (lens_dir / "friction.json").write_text(payload_json, encoding="utf-8")

    def _cfg(self, d):
        _pack(d, {"frictionCategories": ["tooling", "docs"]}, analysis={"title": "t"})

    def test_top_level_list_is_gap_not_crash(self):
        with tempfile.TemporaryDirectory() as d:
            self._cfg(d)
            self._write_raw_friction(d, json.dumps([{"type": "docs"}]))
            gaps = validate_contracts._friction_gaps(config.read_config(), d)
            self.assertTrue(gaps)
            self.assertTrue(any("malformed" in g for g in gaps))

    def test_entries_dict_is_gap_not_crash(self):
        with tempfile.TemporaryDirectory() as d:
            self._cfg(d)
            self._write_raw_friction(d, json.dumps({"entries": {"type": "docs"}}))
            gaps = validate_contracts._friction_gaps(config.read_config(), d)
            self.assertTrue(gaps)
            self.assertTrue(any("entries" in g and "list" in g for g in gaps))

    def test_string_entry_is_gap_not_crash(self):
        with tempfile.TemporaryDirectory() as d:
            self._cfg(d)
            self._write_raw_friction(d, json.dumps({"entries": ["just a string"]}))
            gaps = validate_contracts._friction_gaps(config.read_config(), d)
            self.assertTrue(gaps)
            self.assertTrue(any("entry is not an object" in g for g in gaps))

    def test_entries_null_is_no_gap(self):
        with tempfile.TemporaryDirectory() as d:
            self._cfg(d)
            self._write_raw_friction(d, json.dumps({"entries": None}))
            self.assertEqual(validate_contracts._friction_gaps(config.read_config(), d), [])

    def test_malformed_shapes_never_raise_through_collect_gaps(self):
        for payload in ('[{"type": "docs"}]', '{"entries": {"type": "x"}}',
                        '{"entries": ["str"]}', '{"entries": 42}', '"just a string"'):
            with tempfile.TemporaryDirectory() as d:
                self._cfg(d)
                self._write_raw_friction(d, payload)
                try:
                    gaps = validate_contracts.collect_gaps(d)
                except Exception as exc:  # noqa: BLE001 — the whole point is: it must NOT raise
                    self.fail("collect_gaps raised on malformed friction {!r}: {}".format(payload, exc))
                self.assertTrue(gaps, "malformed friction {!r} should yield a gap".format(payload))


class TestFrictionGateUnderDisabledAnalysis(unittest.TestCase):
    """The friction gate's data source is the LENS (Step 4.7 reads analysisLenses
    independently of the evaluator's analysis:false), so it must run REGARDLESS of the
    evaluator's `disabled` flag. Guarding it behind `disabled` would ship a bad taxonomy
    un-gated whenever analysis is off — a Silent Fallback."""

    def test_disabled_analysis_still_gates_bad_friction_type(self):
        with tempfile.TemporaryDirectory() as d:
            _pack(d, {"frictionCategories": ["tooling", "docs"]},
                  analysis={"title": "disabled", "disabled": True})
            _write_friction_lens(d, [{"friction": "x", "impact": "y", "type": "vibes"}])
            gaps = validate_contracts.collect_gaps(d)
            self.assertTrue(any("vibes" in g for g in gaps),
                            "friction gate must fire even when analysis is disabled")


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
            # The gap message embeds git's raw --show-toplevel output, which on
            # Windows is the LONG name with forward slashes. str(repo_a) can be
            # the 8.3 SHORT name (RUNNER~1 on CI), so canon_root() it first to
            # expand short->long, then _norm_slashes() both sides to fold the
            # slash/case difference. On POSIX canon_root is just realpath and
            # _norm_slashes a lowercase, so this stays a plain match there.
            self.assertIn(_norm_slashes(canon_root(str(repo_a))), _norm_slashes(joined))
            self.assertIn(_norm_slashes(canon_root(str(repo_b))), _norm_slashes(joined))

    def test_two_write_repos_all_accounted_no_gap(self):
        with tempfile.TemporaryDirectory() as d:
            repo_a = _init_repo(Path(d) / "repo_a")
            repo_b = _init_repo(Path(d) / "repo_b")
            (repo_a / "a.py").write_text("x = 1\n", encoding="utf-8")
            (repo_b / "b.py").write_text("y = 2\n", encoding="utf-8")
            _write_transcript(d, [_edit_entry(repo_a, "a.py"), _edit_entry(repo_b, "b.py")])
            # canon_root(str(repo)), not os.path.realpath: this simulates what
            # repo_diffs.py itself now writes into repo-diffs.json (see its
            # canon_root() call on git's --show-toplevel), so the fixture stays
            # faithful to production on every platform, not just POSIX.
            self._diffs(d, repos=[{"repoRoot": canon_root(str(repo_a))}],
                        skipped=[{"repoRoot": canon_root(str(repo_b))}])
            self.assertEqual(validate_contracts._repo_coverage_gaps(d), [])

    def test_two_write_repos_one_unaccounted_is_gap(self):
        with tempfile.TemporaryDirectory() as d:
            repo_a = _init_repo(Path(d) / "repo_a")
            repo_b = _init_repo(Path(d) / "repo_b")
            (repo_a / "a.py").write_text("x = 1\n", encoding="utf-8")
            (repo_b / "b.py").write_text("y = 2\n", encoding="utf-8")
            _write_transcript(d, [_edit_entry(repo_a, "a.py"), _edit_entry(repo_b, "b.py")])
            self._diffs(d, repos=[{"repoRoot": canon_root(str(repo_a))}])
            gaps = validate_contracts._repo_coverage_gaps(d)
            joined_norm = _norm_slashes(" ".join(gaps))
            # canon_root() the expected paths to the long form before folding, so
            # a Windows 8.3 short tmpdir name matches the long name in the message.
            self.assertTrue(_norm_slashes(canon_root(str(repo_b))) in joined_norm)
            self.assertFalse(_norm_slashes(canon_root(str(repo_a))) in joined_norm)

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
            self._diffs(d, repos=[{"repoRoot": canon_root(str(repo_a))}],
                        skipped=[{"repoRoot": canon_root(str(repo_b))}],
                        errors=[{"repoRoot": canon_root(str(repo_a)), "error": "base ref not found"}])
            gaps = validate_contracts._repo_coverage_gaps(d)
            self.assertTrue(any(
                _norm_slashes(canon_root(str(repo_a))) in _norm_slashes(g)
                and "base ref not found" in g
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
            self.assertTrue(any(
                _norm_slashes(canon_root(str(repo_a))) in _norm_slashes(g)
                or _norm_slashes(canon_root(str(repo_b))) in _norm_slashes(g)
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
                json.dumps({"title": "t"}), encoding="utf-8")
            _write_friction_lens(d, [{"friction": "x", "impact": "y", "type": "vibes"}])
            gaps = validate_contracts.collect_gaps(d)
            self.assertTrue(any("vibes" in g for g in gaps))


if __name__ == "__main__":
    unittest.main()
