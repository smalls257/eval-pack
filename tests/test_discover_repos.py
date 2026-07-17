import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import discover_repos  # noqa: E402


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


def _write_transcript(path, entries):
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")


class DiscoverReposTests(unittest.TestCase):
    def test_single_repo_from_cwd(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _init_repo(Path(d) / "repo")
            t = Path(d) / "transcript.jsonl"
            _write_transcript(t, [
                {"type": "user", "cwd": str(repo), "gitBranch": "main"},
                {"type": "assistant", "cwd": str(repo)},
            ])
            got = discover_repos.discover(str(t))
            self.assertEqual(len(got), 1)
            entry = got[0]
            self.assertEqual(Path(entry["repoRoot"]).resolve(), repo.resolve())
            self.assertTrue(entry["branch"])
            self.assertTrue(entry["head"])
            self.assertIn("cwd", entry["signals"])

    def test_file_paths_discover_second_repo(self):
        with tempfile.TemporaryDirectory() as d:
            repo_a = _init_repo(Path(d) / "repo_a")
            repo_b = _init_repo(Path(d) / "repo_b")
            (repo_b / "file.py").write_text("x = 1\n", encoding="utf-8")
            t = Path(d) / "transcript.jsonl"
            _write_transcript(t, [
                {"type": "user", "cwd": str(repo_a), "gitBranch": "main"},
                {
                    "type": "assistant",
                    "cwd": str(repo_a),
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "name": "Edit",
                                "input": {"file_path": str(repo_b / "file.py")},
                            }
                        ]
                    },
                },
            ])
            got = discover_repos.discover(str(t))
            roots = {Path(e["repoRoot"]).resolve() for e in got}
            self.assertEqual(roots, {repo_a.resolve(), repo_b.resolve()})
            entry_b = next(e for e in got if Path(e["repoRoot"]).resolve() == repo_b.resolve())
            self.assertIn("file_path", entry_b["signals"])

    def test_cd_target_discovered(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _init_repo(Path(d) / "repo")
            other = Path(d) / "other"
            other.mkdir()
            t = Path(d) / "transcript.jsonl"
            _write_transcript(t, [
                {
                    "type": "assistant",
                    "cwd": str(other),
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "name": "Bash",
                                "input": {"command": f"cd {repo} && ls"},
                            }
                        ]
                    },
                },
            ])
            got = discover_repos.discover(str(t))
            roots = {Path(e["repoRoot"]).resolve() for e in got}
            self.assertIn(repo.resolve(), roots)
            entry = next(e for e in got if Path(e["repoRoot"]).resolve() == repo.resolve())
            self.assertIn("cd", entry["signals"])

    def test_two_worktrees_same_repo_are_separate(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _init_repo(Path(d) / "repo")
            _run(["git", "branch", "feat"], cwd=str(repo))
            wt = Path(d) / "wt"
            _run(["git", "worktree", "add", str(wt), "feat"], cwd=str(repo))
            t = Path(d) / "transcript.jsonl"
            _write_transcript(t, [
                {"type": "user", "cwd": str(repo), "gitBranch": "main"},
                {"type": "user", "cwd": str(wt), "gitBranch": "feat"},
            ])
            got = discover_repos.discover(str(t))
            roots = {Path(e["repoRoot"]).resolve() for e in got}
            self.assertEqual(roots, {repo.resolve(), wt.resolve()})
            branches = {e["branch"] for e in got}
            self.assertEqual(branches, {"main", "feat"})
            common_dirs = {e["gitCommonDir"] for e in got}
            self.assertEqual(len(common_dirs), 1)

    def test_nonexistent_and_nongit_dirs_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            nongit = Path(d) / "nongit"
            nongit.mkdir()
            t = Path(d) / "transcript.jsonl"
            _write_transcript(t, [
                {"type": "user", "cwd": str(nongit)},
                {"type": "user", "cwd": "/no/such/dir"},
            ])
            got = discover_repos.discover(str(t))
            self.assertEqual(got, [])

    def test_malformed_lines_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _init_repo(Path(d) / "repo")
            t = Path(d) / "transcript.jsonl"
            t.write_text(
                json.dumps({"type": "user", "cwd": str(repo), "gitBranch": "main"}) + "\n"
                + "not valid json {{{\n"
                + "\n",
                encoding="utf-8",
            )
            got = discover_repos.discover(str(t))
            self.assertEqual(len(got), 1)

    def test_touchcount_and_sort(self):
        with tempfile.TemporaryDirectory() as d:
            repo_a = _init_repo(Path(d) / "repo_a")
            repo_b = _init_repo(Path(d) / "repo_b")
            (repo_b / "file.py").write_text("x = 1\n", encoding="utf-8")
            t = Path(d) / "transcript.jsonl"
            entries = [{"type": "user", "cwd": str(repo_b), "gitBranch": "main"}]
            # repo_a touched by many more cwd entries than repo_b
            for _ in range(5):
                entries.append({"type": "user", "cwd": str(repo_a), "gitBranch": "main"})
            _write_transcript(t, entries)
            got = discover_repos.discover(str(t))
            self.assertEqual(Path(got[0]["repoRoot"]).resolve(), repo_a.resolve())
            self.assertGreater(got[0]["touchCount"], got[1]["touchCount"])

    def test_cli_prints_json_array(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _init_repo(Path(d) / "repo")
            t = Path(d) / "transcript.jsonl"
            _write_transcript(t, [{"type": "user", "cwd": str(repo), "gitBranch": "main"}])
            script = str(Path(__file__).resolve().parent.parent / "scripts" / "discover_repos.py")
            out = subprocess.run(
                [sys.executable, script, str(t)], capture_output=True, text=True
            )
            self.assertEqual(out.returncode, 0)
            parsed = json.loads(out.stdout)
            self.assertIsInstance(parsed, list)
            self.assertEqual(len(parsed), 1)


if __name__ == "__main__":
    unittest.main()
