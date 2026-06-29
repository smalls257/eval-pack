import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import discover_sessions  # noqa: E402


def _init_repo(path):
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "-C", str(path), "init", "-q"], check=True)
    return path


def _write_session(projdir, sid, entries):
    projdir.mkdir(parents=True, exist_ok=True)
    (projdir / f"{sid}.jsonl").write_text(
        "\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")


class DiscoverTests(unittest.TestCase):
    def _setup(self, d):
        repo = _init_repo(Path(d) / "repo")
        cfg = Path(d) / "cfg"
        slug = discover_sessions._encode_project_slug(
            discover_sessions._worktree_dirs(str(repo))[0])
        proj = cfg / "projects" / slug
        return repo, cfg, proj

    def test_finds_unarchived_session_with_preview(self):
        with tempfile.TemporaryDirectory() as d:
            repo, cfg, proj = self._setup(d)
            _write_session(proj, "sX", [
                {"type": "user", "uuid": "u1", "gitBranch": "main",
                 "timestamp": "2026-06-01T10:00:00Z",
                 "message": {"content": [{"type": "text", "text": "do the thing"}]}},
                {"type": "assistant", "uuid": "u2",
                 "timestamp": "2026-06-01T10:01:00Z",
                 "message": {"content": [{"type": "text", "text": "ok"}]}},
            ])
            got = discover_sessions.discover(str(repo), config_dir=cfg)
            self.assertEqual(len(got), 1)
            c = got[0]
            self.assertEqual(c["sessionId"], "sX")
            self.assertEqual(c["firstPrompt"], "do the thing")
            self.assertEqual(c["branches"], ["main"])
            self.assertEqual(c["msgCount"], 2)

    def test_excludes_already_archived(self):
        with tempfile.TemporaryDirectory() as d:
            repo, cfg, proj = self._setup(d)
            _write_session(proj, "sX", [{"uuid": "u1", "timestamp": "t"}])
            adir = repo / ".eval-packs" / "sessions"
            adir.mkdir(parents=True)
            (adir / "sX.jsonl").write_text('{"uuid":"u1"}\n', encoding="utf-8")
            got = discover_sessions.discover(str(repo), config_dir=cfg)
            self.assertEqual(got, [])

    def test_empty_when_no_project_dir(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _init_repo(Path(d) / "repo")
            cfg = Path(d) / "cfg"
            self.assertEqual(discover_sessions.discover(str(repo), config_dir=cfg), [])

    def test_first_prompt_skips_angle_bracket_content(self):
        with tempfile.TemporaryDirectory() as d:
            repo, cfg, proj = self._setup(d)
            _write_session(proj, "sY", [
                {"type": "user", "uuid": "u0",
                 "timestamp": "2026-06-01T09:00:00Z",
                 "message": {"content": [{"type": "text", "text": "<command-stuff>"}]}},
                {"type": "user", "uuid": "u1",
                 "timestamp": "2026-06-01T09:01:00Z",
                 "message": {"content": [{"type": "text", "text": "real ask"}]}},
            ])
            got = discover_sessions.discover(str(repo), config_dir=cfg)
            self.assertEqual(got[0]["firstPrompt"], "real ask")


class SlugEncodingTests(unittest.TestCase):
    def test_matches_claude_code_rule_cross_platform(self):
        enc = discover_sessions._encode_project_slug
        # macOS/Linux simple
        self.assertEqual(enc("/Users/x/Code/eval-pack"), "-Users-x-Code-eval-pack")
        # dotted dir (macOS worktree): /. -> -- , matching real CC dir names
        self.assertEqual(enc("/Users/x/p/.claude/wt"), "-Users-x-p--claude-wt")
        # Windows backslash path: drive colon + separators -> -
        self.assertEqual(enc("C:\\Users\\x\\Code\\eval-pack"),
                         "C--Users-x-Code-eval-pack")
        # Windows git-style forward slashes encode identically
        self.assertEqual(enc("C:/Users/x/Code/eval-pack"),
                         "C--Users-x-Code-eval-pack")


if __name__ == "__main__":
    unittest.main()
