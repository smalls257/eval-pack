import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import archive_session  # noqa: E402


def _init_repo(path):
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "-C", str(path), "init", "-q"], check=True)
    return path


class ArchiveSubagentsTests(unittest.TestCase):
    def test_subagents_dir_is_archived(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _init_repo(Path(d) / "repo")
            ccdir = Path(d) / "cc"
            ccdir.mkdir()
            tr = ccdir / "sess1.jsonl"
            tr.write_text('{"uuid":"u1","gitBranch":"main"}\n', encoding="utf-8")
            sub = ccdir / "sess1" / "subagents"
            sub.mkdir(parents=True)
            (sub / "agent-aaa.jsonl").write_text('{"uuid":"s1"}\n', encoding="utf-8")
            res = archive_session.archive_session({
                "session_id": "sess1", "transcript_path": str(tr),
                "cwd": str(repo), "reason": "other",
            })
            self.assertEqual(res["status"], "archived")
            dest_sub = (repo / ".eval-packs" / "sessions" / "sess1"
                        / "subagents" / "agent-aaa.jsonl")
            self.assertTrue(dest_sub.is_file())
            self.assertEqual(dest_sub.read_text(), '{"uuid":"s1"}\n')

    def test_no_subagents_dir_is_fine(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _init_repo(Path(d) / "repo")
            tr = Path(d) / "sess2.jsonl"
            tr.write_text('{"uuid":"u1"}\n', encoding="utf-8")
            res = archive_session.archive_session({
                "session_id": "sess2", "transcript_path": str(tr),
                "cwd": str(repo), "reason": "other",
            })
            self.assertEqual(res["status"], "archived")
            self.assertFalse((repo / ".eval-packs" / "sessions" / "sess2").is_dir())


if __name__ == "__main__":
    unittest.main()
