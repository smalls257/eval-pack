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


class ExtraPathsTests(unittest.TestCase):
    def test_extra_paths_join_the_merge(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _init_repo(Path(d) / "repo")
            current = Path(d) / "current.jsonl"
            _write(current, [{"uuid": "c1", "timestamp": "2026-06-03T00:00:00Z"}])
            picked = Path(d) / "picked.jsonl"
            _write(picked, [{"uuid": "p1", "timestamp": "2026-06-01T00:00:00Z"}])
            out = Path(d) / "merged.jsonl"
            res = build_conversation.build(
                str(repo), str(current), out, extra_paths=[str(picked)])
            self.assertEqual(res["sessions"], 2)
            uuids = [json.loads(l)["uuid"]
                     for l in out.read_text().splitlines() if l.strip()]
            self.assertEqual(uuids, ["p1", "c1"])

    def test_extra_paths_deduped_against_archived(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _init_repo(Path(d) / "repo")
            sdir = repo / ".eval-packs" / "sessions"
            sdir.mkdir(parents=True)
            archived = sdir / "a.jsonl"
            _write(archived, [{"uuid": "a1", "timestamp": "t"}])
            out = Path(d) / "merged.jsonl"
            res = build_conversation.build(
                str(repo), "", out, extra_paths=[str(archived)])
            self.assertEqual(res["sessions"], 1)
            self.assertEqual(res["entries"], 1)

    def test_default_no_extra_paths_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _init_repo(Path(d) / "repo")
            current = Path(d) / "current.jsonl"
            _write(current, [{"uuid": "c1", "timestamp": "t"}])
            out = Path(d) / "merged.jsonl"
            res = build_conversation.build(str(repo), str(current), out)
            self.assertEqual(res["sessions"], 1)


if __name__ == "__main__":
    unittest.main()
