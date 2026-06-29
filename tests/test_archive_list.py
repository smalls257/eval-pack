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


class ListArchivedTests(unittest.TestCase):
    def test_empty_when_no_store(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _init_repo(Path(d) / "repo")
            self.assertEqual(archive_session.list_archived_sessions(repo), [])

    def test_lists_jsonl_files_as_truth(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _init_repo(Path(d) / "repo")
            sdir = repo / ".eval-packs" / "sessions"
            sdir.mkdir(parents=True)
            (sdir / "s1.jsonl").write_text('{"uuid":"u1"}\n', encoding="utf-8")
            (sdir / "s2.jsonl").write_text('{"uuid":"u2"}\n', encoding="utf-8")
            (sdir / "index.json").write_text(
                json.dumps({"sessions": {"s1": {}}}), encoding="utf-8")
            names = sorted(p.name for p in
                           archive_session.list_archived_sessions(repo))
            self.assertEqual(names, ["s1.jsonl", "s2.jsonl"])


if __name__ == "__main__":
    unittest.main()
