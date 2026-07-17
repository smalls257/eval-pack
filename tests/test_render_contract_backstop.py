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


def _run_git(cmd, cwd):
    out = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"{cmd} failed: {out.stderr}")
    return out.stdout


def _init_repo(path):
    path.mkdir(parents=True, exist_ok=True)
    _run_git(["git", "init", "-q"], path)
    _run_git(["git", "config", "user.email", "t@example.com"], path)
    _run_git(["git", "config", "user.name", "T"], path)
    _run_git(["git", "commit", "--allow-empty", "-q", "-m", "init"], path)
    return path


def _edit_entry(repo, filename):
    return {
        "type": "assistant",
        "cwd": str(repo),
        "message": {"content": [
            {"type": "tool_use", "name": "Edit",
             "input": {"file_path": str(repo / filename)}},
        ]},
    }


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


class TestMultiRepoRenderRefusal(unittest.TestCase):
    """End-to-end: a real 2-write-repo pack with NO repo-diffs.json must make
    render_html.py REFUSE (the coverage gate) and PRESERVE the pack dir. Pins the
    deterministic backstop in CI so it can't regress into a silent single-diff render."""

    def test_render_refuses_missing_repo_diffs(self):
        with tempfile.TemporaryDirectory() as out:
            sid = "multirepo"
            pack = Path(out) / sid
            pack.mkdir(parents=True)
            # Two REAL git repos the session "edited".
            repo_a = _init_repo(pack / "repo_a")
            repo_b = _init_repo(pack / "repo_b")
            (repo_a / "a.py").write_text("x = 1\n", encoding="utf-8")
            (repo_b / "b.py").write_text("y = 2\n", encoding="utf-8")

            base = dict(json.loads(json.dumps(config.DEFAULTS)))
            (pack / "eval-config.json").write_text(json.dumps(base), encoding="utf-8")
            # transcript: two Edit tool_uses (turns for validate_pack, write signals for the gate).
            (pack / "transcript.jsonl").write_text(
                "\n".join(json.dumps(e) for e in
                          [_edit_entry(repo_a, "a.py"), _edit_entry(repo_b, "b.py")]) + "\n",
                encoding="utf-8")
            # Everything else valid so the ONLY refusal reason is the missing repo-diffs.json.
            (pack / "metrics.json").write_text(json.dumps({"turnCount": 2}), encoding="utf-8")
            (pack / "analysis.json").write_text(json.dumps({"title": "t"}), encoding="utf-8")
            (pack / "patterns.json").write_text(json.dumps({"flags": []}), encoding="utf-8")
            (pack / "test-results.json").write_text(json.dumps({"verdict": "none"}), encoding="utf-8")
            # NO repo-diffs.json on purpose.

            r = _render(out, sid, pack)
            combined = (r.stdout or "") + (r.stderr or "")
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("repo-diffs.json is missing", combined)
            # Contract gaps PRESERVE the pack dir (evidence for the fix).
            self.assertTrue(pack.is_dir())
            self.assertTrue((pack / "analysis.json").is_file())


if __name__ == "__main__":
    unittest.main()
