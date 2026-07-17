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
            self.assertIn("write", entry_b["signals"])

    def test_write_vs_read_signal_split(self):
        with tempfile.TemporaryDirectory() as d:
            repo_a = _init_repo(Path(d) / "repo_a")
            repo_b = _init_repo(Path(d) / "repo_b")
            (repo_a / "edited.py").write_text("x = 1\n", encoding="utf-8")
            (repo_b / "read.py").write_text("y = 2\n", encoding="utf-8")
            t = Path(d) / "transcript.jsonl"
            _write_transcript(t, [
                {
                    "type": "assistant",
                    "cwd": str(repo_a),
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "name": "Edit",
                                "input": {"file_path": str(repo_a / "edited.py")},
                            }
                        ]
                    },
                },
                {
                    "type": "assistant",
                    "cwd": str(repo_a),
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "name": "Read",
                                "input": {"file_path": str(repo_b / "read.py")},
                            }
                        ]
                    },
                },
            ])
            got = discover_repos.discover(str(t))
            entry_a = next(e for e in got if Path(e["repoRoot"]).resolve() == repo_a.resolve())
            entry_b = next(e for e in got if Path(e["repoRoot"]).resolve() == repo_b.resolve())
            self.assertIn("write", entry_a["signals"])
            self.assertIn("read", entry_b["signals"])
            self.assertNotIn("write", entry_b["signals"])

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

    def test_cd_false_positive_rejected_by_isdir(self):
        # `cd` inside a quoted echo yields a bogus token (`/definitely/not/real"`)
        # that the is_dir() guard must reject before any git call runs.
        with tempfile.TemporaryDirectory() as d:
            t = Path(d) / "transcript.jsonl"
            _write_transcript(t, [
                {
                    "type": "assistant",
                    "cwd": str(Path(d)),  # a non-git tempdir; itself not a repo
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "name": "Bash",
                                "input": {"command": 'echo "x; cd /definitely/not/real"'},
                            }
                        ]
                    },
                },
            ])
            got = discover_repos.discover(str(t))
            self.assertEqual(got, [])

    def test_git_argv_carries_hardening_flags(self):
        argv = discover_repos._git_argv(["rev-parse", "--show-toplevel"], "/some/dir")
        self.assertEqual(argv[0], "git")
        # Hardening flags precede -C so they apply to the top-level git process.
        self.assertIn("core.fsmonitor=", argv)
        self.assertIn("core.pager=cat", argv)
        self.assertIn("--no-optional-locks", argv)
        self.assertLess(argv.index("--no-optional-locks"), argv.index("-C"))
        self.assertEqual(argv[-2:], ["rev-parse", "--show-toplevel"])

    def test_hardened_env_neutralizes_external_config(self):
        env = discover_repos._hardened_env()
        self.assertEqual(env["GIT_OPTIONAL_LOCKS"], "0")
        self.assertEqual(env["GIT_CONFIG_GLOBAL"], "/dev/null")
        self.assertEqual(env["GIT_CONFIG_SYSTEM"], "/dev/null")

    def test_discover_write_repos_only_resolves_write_dirs(self):
        # Edit under repo A (write signal) + Read under repo B (read signal only).
        # discover_write_repos must return ONLY A, and must never git-resolve B's dir.
        with tempfile.TemporaryDirectory() as d:
            repo_a = _init_repo(Path(d) / "repo_a")
            repo_b = _init_repo(Path(d) / "repo_b")
            (repo_a / "a.py").write_text("x = 1\n", encoding="utf-8")
            (repo_b / "b.py").write_text("y = 2\n", encoding="utf-8")
            t = Path(d) / "transcript.jsonl"
            _write_transcript(t, [
                {
                    "type": "assistant",
                    "cwd": str(repo_a),
                    "message": {"content": [
                        {"type": "tool_use", "name": "Edit",
                         "input": {"file_path": str(repo_a / "a.py")}},
                    ]},
                },
                {
                    "type": "assistant",
                    "cwd": str(repo_a),
                    "message": {"content": [
                        {"type": "tool_use", "name": "Read",
                         "input": {"file_path": str(repo_b / "b.py")}},
                    ]},
                },
            ])

            # Spy on the resolver to prove B's dir is never git-resolved.
            resolved_dirs = []
            real_resolve = discover_repos._resolve_repo

            def spy(dir_path):
                resolved_dirs.append(str(Path(dir_path).resolve()))
                return real_resolve(dir_path)

            discover_repos._resolve_repo = spy
            try:
                got = discover_repos.discover_write_repos(str(t))
            finally:
                discover_repos._resolve_repo = real_resolve

            roots = {Path(e["repoRoot"]).resolve() for e in got}
            self.assertEqual(roots, {repo_a.resolve()})
            entry = got[0]
            self.assertEqual(entry["signals"], ["write"])
            self.assertTrue(entry["branch"])
            self.assertTrue(entry["head"])
            self.assertIn("gitCommonDir", entry)
            # B's dir must never have reached the git resolver.
            self.assertNotIn(str(repo_b.resolve()), resolved_dirs)

    def test_discover_write_repos_dedups_and_counts(self):
        # Multiple Edit file_paths under the SAME repo (different subdirs/files)
        # collapse to one entry with touchCount == number of write file_paths.
        with tempfile.TemporaryDirectory() as d:
            repo = _init_repo(Path(d) / "repo")
            (repo / "sub").mkdir()
            paths = [repo / "a.py", repo / "b.py", repo / "sub" / "c.py"]
            for p in paths:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("x = 1\n", encoding="utf-8")
            t = Path(d) / "transcript.jsonl"
            _write_transcript(t, [
                {
                    "type": "assistant",
                    "cwd": str(repo),
                    "message": {"content": [
                        {"type": "tool_use", "name": "Edit",
                         "input": {"file_path": str(p)}},
                    ]},
                }
                for p in paths
            ])
            got = discover_repos.discover_write_repos(str(t))
            self.assertEqual(len(got), 1)
            self.assertEqual(Path(got[0]["repoRoot"]).resolve(), repo.resolve())
            self.assertEqual(got[0]["touchCount"], len(paths))
            self.assertEqual(got[0]["signals"], ["write"])

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
