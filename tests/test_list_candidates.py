import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import list_candidates  # noqa: E402
import discover_sessions  # noqa: E402


def _init_repo(path):
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "-C", str(path), "init", "-q"], check=True)
    return path


def _write(path, entries):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")


class ListCandidatesTests(unittest.TestCase):
    def test_merges_sources_flags_relevance_excludes_current(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _init_repo(Path(d) / "repo")
            cfg = Path(d) / "cfg"
            adir = repo / ".eval-packs" / "sessions"
            _write(adir / "arch1.jsonl",
                   [{"uuid": "a1", "gitBranch": "main", "timestamp": "2026-06-01T00:00:00Z",
                     "type": "user", "message": {"content": [{"type": "text", "text": "archived work"}]}}])
            slug = discover_sessions._encode_project_slug(
                discover_sessions._worktree_dirs(str(repo))[0])
            proj = cfg / "projects" / slug
            _write(proj / "disc1.jsonl",
                   [{"uuid": "d1", "gitBranch": "feature/z", "timestamp": "2026-06-02T00:00:00Z",
                     "type": "user", "message": {"content": [{"type": "text", "text": "other branch"}]}}])
            _write(proj / "curr.jsonl",
                   [{"uuid": "x1", "gitBranch": "main", "timestamp": "2026-06-03T00:00:00Z"}])

            cands = list_candidates.list_candidates(
                str(repo), "curr", "main", config_dir=cfg)
            by_id = {c["sessionId"]: c for c in cands}
            self.assertNotIn("curr", by_id)
            self.assertEqual(by_id["arch1"]["source"], "archive")
            self.assertTrue(by_id["arch1"]["relevant"])
            self.assertEqual(by_id["disc1"]["source"], "discovered")
            self.assertFalse(by_id["disc1"]["relevant"])
            self.assertTrue(cands[0]["relevant"])

    def test_empty_when_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _init_repo(Path(d) / "repo")
            cfg = Path(d) / "cfg"
            self.assertEqual(
                list_candidates.list_candidates(str(repo), "x", "main", config_dir=cfg),
                [])


if __name__ == "__main__":
    unittest.main()
