import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import archive_session  # noqa: E402


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True, text=True)


def _init_repo(path):
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "t@t.t")
    _git(path, "config", "user.name", "t")
    return path


class ResolveRepoRootTests(unittest.TestCase):
    def test_resolves_root_from_subdir(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _init_repo(Path(d) / "repo")
            sub = repo / "a" / "b"
            sub.mkdir(parents=True)
            self.assertEqual(archive_session.resolve_repo_root(str(sub)),
                             repo.resolve())

    def test_returns_none_outside_repo(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(archive_session.resolve_repo_root(d))


class ArchiveSessionTests(unittest.TestCase):
    def _payload(self, repo, transcript, sid="sess-1"):
        return {
            "session_id": sid,
            "transcript_path": str(transcript),
            "cwd": str(repo),
            "hook_event_name": "SessionEnd",
            "reason": "other",
        }

    def _make_transcript(self, path, lines):
        path.write_text("\n".join(json.dumps(o) for o in lines) + "\n",
                        encoding="utf-8")

    def test_copies_transcript_and_writes_index(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _init_repo(Path(d) / "repo")
            tr = Path(d) / "orig.jsonl"
            self._make_transcript(tr, [{"uuid": "u1", "gitBranch": "main"}])
            res = archive_session.archive_session(self._payload(repo, tr))
            self.assertEqual(res["status"], "archived")
            dest = repo / ".eval-packs" / "sessions" / "sess-1.jsonl"
            self.assertTrue(dest.is_file())
            self.assertEqual(dest.read_text(), tr.read_text())
            index = json.loads(
                (repo / ".eval-packs" / "sessions" / "index.json").read_text())
            self.assertIn("sess-1", index["sessions"])
            self.assertEqual(index["sessions"]["sess-1"]["branch"], "main")

    def test_overwrite_is_idempotent_and_keeps_one_entry(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _init_repo(Path(d) / "repo")
            tr = Path(d) / "orig.jsonl"
            self._make_transcript(tr, [{"uuid": "u1"}])
            archive_session.archive_session(self._payload(repo, tr))
            self._make_transcript(tr, [{"uuid": "u1"}, {"uuid": "u2"}])
            archive_session.archive_session(self._payload(repo, tr))
            dest = repo / ".eval-packs" / "sessions" / "sess-1.jsonl"
            self.assertEqual(len(dest.read_text().strip().splitlines()), 2)
            index = json.loads(
                (repo / ".eval-packs" / "sessions" / "index.json").read_text())
            self.assertEqual(list(index["sessions"]), ["sess-1"])

    def test_noop_outside_repo(self):
        with tempfile.TemporaryDirectory() as d:
            tr = Path(d) / "orig.jsonl"
            self._make_transcript(tr, [{"uuid": "u1"}])
            res = archive_session.archive_session({
                "session_id": "s", "transcript_path": str(tr),
                "cwd": d, "reason": "other",
            })
            self.assertEqual(res["status"], "skipped-no-repo")

    def test_worktree_maps_to_same_root(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _init_repo(Path(d) / "repo")
            (repo / "f.txt").write_text("x", encoding="utf-8")
            _git(repo, "add", "-A")
            _git(repo, "commit", "-qm", "init")
            wt = Path(d) / "wt"
            _git(repo, "worktree", "add", "-q", str(wt))
            self.assertEqual(archive_session.resolve_repo_root(str(wt)),
                             repo.resolve())

    def test_skipped_invalid_session_id(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _init_repo(Path(d) / "repo")
            tr = Path(d) / "orig.jsonl"
            self._make_transcript(tr, [{"uuid": "u1"}])
            res = archive_session.archive_session(
                self._payload(repo, tr, sid="../evil"))
            self.assertEqual(res["status"], "skipped-invalid-session-id")

    def test_skipped_missing_transcript_path(self):
        res = archive_session.archive_session(
            {"session_id": "s", "cwd": ".", "reason": "other"})
        self.assertEqual(res["status"], "skipped-no-transcript")


if __name__ == "__main__":
    unittest.main()
