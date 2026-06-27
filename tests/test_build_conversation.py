import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import build_conversation  # noqa: E402


def _init_repo(path):
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "-C", str(path), "init", "-q"], check=True)
    return path


def _write(path, entries):
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")


class BuildConversationTests(unittest.TestCase):
    def test_merges_archived_and_current(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _init_repo(Path(d) / "repo")
            sdir = repo / ".eval-packs" / "sessions"
            sdir.mkdir(parents=True)
            _write(sdir / "old.jsonl",
                   [{"uuid": "u1", "timestamp": "2026-06-01T10:00:00Z"}])
            current = Path(d) / "current.jsonl"
            _write(current, [{"uuid": "u2", "timestamp": "2026-06-02T10:00:00Z"}])
            out = Path(d) / "merged.jsonl"
            res = build_conversation.build(str(repo), str(current), out)
            self.assertEqual(res["sessions"], 2)
            uuids = [json.loads(l)["uuid"]
                     for l in out.read_text().splitlines() if l.strip()]
            self.assertEqual(uuids, ["u1", "u2"])

    def test_current_only_when_no_archive(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _init_repo(Path(d) / "repo")
            current = Path(d) / "current.jsonl"
            _write(current, [{"uuid": "u1", "timestamp": "t"}])
            out = Path(d) / "merged.jsonl"
            res = build_conversation.build(str(repo), str(current), out)
            self.assertEqual(res["sessions"], 1)
            self.assertEqual(res["entries"], 1)

    def test_no_double_count_when_current_already_archived(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _init_repo(Path(d) / "repo")
            sdir = repo / ".eval-packs" / "sessions"
            sdir.mkdir(parents=True)
            archived = sdir / "live.jsonl"
            _write(archived, [{"uuid": "u1", "timestamp": "t"}])
            out = Path(d) / "merged.jsonl"
            res = build_conversation.build(str(repo), str(archived), out)
            self.assertEqual(res["sessions"], 1)
            self.assertEqual(res["entries"], 1)

    def test_zero_when_nothing_available(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _init_repo(Path(d) / "repo")
            out = Path(d) / "merged.jsonl"
            res = build_conversation.build(str(repo), "", out)
            self.assertEqual(res["sessions"], 0)
            self.assertFalse(out.exists())

    def test_non_git_repo_cwd_uses_current_only(self):
        with tempfile.TemporaryDirectory() as d:
            plain = Path(d) / "plain"   # NOT a git repo
            plain.mkdir()
            current = Path(d) / "current.jsonl"
            _write(current, [{"uuid": "u1", "timestamp": "t"}])
            out = Path(d) / "merged.jsonl"
            res = build_conversation.build(str(plain), str(current), out)
            self.assertEqual(res["sessions"], 1)
            self.assertEqual(res["entries"], 1)


if __name__ == "__main__":
    unittest.main()
