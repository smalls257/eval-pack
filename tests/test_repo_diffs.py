import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import repo_diffs  # noqa: E402

EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


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
    return path


def _commit_all(path, msg):
    _run(["git", "add", "-A"], cwd=str(path))
    _run(["git", "commit", "-q", "-m", msg], cwd=str(path))


def _rev_parse(path, ref):
    return _run(["git", "rev-parse", ref], cwd=str(path)).strip()


class RepoDiffsTests(unittest.TestCase):
    def test_single_repo_diff_against_base(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _init_repo(Path(d) / "repo")
            (repo / "a.py").write_text("x = 1\n", encoding="utf-8")
            _commit_all(repo, "init")
            base_sha = _rev_parse(repo, "HEAD")

            (repo / "a.py").write_text("x = 1\ny = 2\n", encoding="utf-8")
            (repo / "b.py").write_text("z = 3\n", encoding="utf-8")
            _commit_all(repo, "second")

            selection = {"repos": [{"repoRoot": str(repo), "base": base_sha}]}
            out = repo_diffs.compute(str(Path(d)), selection)

            self.assertEqual(len(out["repos"]), 1)
            entry = out["repos"][0]
            self.assertEqual(entry["baseResolved"], base_sha)
            self.assertEqual(entry["base"], base_sha)
            self.assertEqual(entry["filesChanged"], 2)
            self.assertIn("a.py", entry["files"])
            self.assertIn("b.py", entry["files"])
            self.assertEqual(entry["insertions"], 2)  # y=2 line + z=3 line
            self.assertEqual(entry["deletions"], 0)
            self.assertTrue(entry["stat"])
            self.assertTrue(entry["branch"])
            self.assertEqual(out["skipped"], [])
            self.assertEqual(out["errors"], [])

    def test_empty_tree_base_counts_everything(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _init_repo(Path(d) / "repo")
            (repo / "a.py").write_text("x = 1\n", encoding="utf-8")
            (repo / "b.py").write_text("y = 2\n", encoding="utf-8")
            _commit_all(repo, "init")

            selection = {"repos": [{"repoRoot": str(repo), "base": EMPTY_TREE_SHA}]}
            out = repo_diffs.compute(str(Path(d)), selection)

            entry = out["repos"][0]
            self.assertEqual(entry["filesChanged"], 2)
            self.assertEqual(set(entry["files"]), {"a.py", "b.py"})
            self.assertEqual(entry["insertions"], 2)
            self.assertEqual(entry["deletions"], 0)

    def test_uncommitted_changes_included(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _init_repo(Path(d) / "repo")
            (repo / "a.py").write_text("x = 1\n", encoding="utf-8")
            _commit_all(repo, "init")
            base_sha = _rev_parse(repo, "HEAD")

            # uncommitted edit
            (repo / "a.py").write_text("x = 1\ny = 2\n", encoding="utf-8")

            selection = {"repos": [{"repoRoot": str(repo), "base": base_sha}]}
            out = repo_diffs.compute(str(Path(d)), selection)

            entry = out["repos"][0]
            self.assertIn("a.py", entry["files"])
            self.assertEqual(entry["insertions"], 1)

    def test_bad_base_becomes_error_not_crash(self):
        with tempfile.TemporaryDirectory() as d:
            repo_a = _init_repo(Path(d) / "repo_a")
            (repo_a / "a.py").write_text("x = 1\n", encoding="utf-8")
            _commit_all(repo_a, "init")
            good_base = _rev_parse(repo_a, "HEAD")

            repo_b = _init_repo(Path(d) / "repo_b")
            (repo_b / "b.py").write_text("y = 1\n", encoding="utf-8")
            _commit_all(repo_b, "init")

            selection = {"repos": [
                {"repoRoot": str(repo_a), "base": good_base},
                {"repoRoot": str(repo_b), "base": "no-such-ref"},
            ]}
            out = repo_diffs.compute(str(Path(d)), selection)

            self.assertEqual(len(out["repos"]), 1)
            self.assertEqual(out["repos"][0]["repoRoot"], str(repo_a))
            self.assertEqual(len(out["errors"]), 1)
            err = out["errors"][0]
            self.assertEqual(err["repoRoot"], str(repo_b))
            self.assertIn("base ref not found", err["error"])

    def test_skip_recorded(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _init_repo(Path(d) / "repo")
            (repo / "a.py").write_text("x = 1\n", encoding="utf-8")
            _commit_all(repo, "init")

            selection = {"repos": [{"repoRoot": str(repo), "base": None, "skip": True}]}
            out = repo_diffs.compute(str(Path(d)), selection)

            self.assertEqual(out["repos"], [])
            self.assertEqual(len(out["skipped"]), 1)
            self.assertEqual(out["skipped"][0]["repoRoot"], str(repo))
            self.assertEqual(out["errors"], [])

    def test_binary_file_handled(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _init_repo(Path(d) / "repo")
            (repo / "a.py").write_text("x = 1\n", encoding="utf-8")
            _commit_all(repo, "init")
            base_sha = _rev_parse(repo, "HEAD")

            (repo / "blob.bin").write_bytes(bytes([0, 1, 2, 255, 0, 254]))
            _commit_all(repo, "add binary")

            selection = {"repos": [{"repoRoot": str(repo), "base": base_sha}]}
            out = repo_diffs.compute(str(Path(d)), selection)

            entry = out["repos"][0]
            self.assertEqual(entry["filesChanged"], 1)
            self.assertIn("blob.bin", entry["files"])

    def test_multiple_repos_one_selection(self):
        with tempfile.TemporaryDirectory() as d:
            repo_a = _init_repo(Path(d) / "repo_a")
            (repo_a / "a.py").write_text("x = 1\n", encoding="utf-8")
            _commit_all(repo_a, "init")
            base_a = _rev_parse(repo_a, "HEAD")
            (repo_a / "a.py").write_text("x = 2\n", encoding="utf-8")
            _commit_all(repo_a, "edit")

            repo_b = _init_repo(Path(d) / "repo_b")
            (repo_b / "b.py").write_text("y = 1\n", encoding="utf-8")
            _commit_all(repo_b, "init")
            base_b = _rev_parse(repo_b, "HEAD")
            (repo_b / "b.py").write_text("y = 2\n", encoding="utf-8")
            _commit_all(repo_b, "edit")

            selection = {"repos": [
                {"repoRoot": str(repo_a), "base": base_a},
                {"repoRoot": str(repo_b), "base": base_b},
            ]}
            out = repo_diffs.compute(str(Path(d)), selection)

            self.assertEqual(len(out["repos"]), 2)
            roots = {r["repoRoot"] for r in out["repos"]}
            self.assertEqual(roots, {str(repo_a), str(repo_b)})

    def test_uses_hardened_git(self):
        """A hostile fsmonitor hook must NOT execute during our diff run."""
        with tempfile.TemporaryDirectory() as d:
            repo = _init_repo(Path(d) / "repo")
            (repo / "a.py").write_text("x = 1\n", encoding="utf-8")
            _commit_all(repo, "init")
            base_sha = _rev_parse(repo, "HEAD")
            (repo / "a.py").write_text("x = 2\n", encoding="utf-8")
            _commit_all(repo, "edit")

            sentinel = Path(d) / "sentinel"
            hook_path = repo / "fsmonitor-hook.sh"
            hook_path.write_text(
                "#!/bin/sh\ntouch \"{}\"\necho '{{\"version\":2,\"clean\":true}}'\n".format(sentinel),
                encoding="utf-8",
            )
            hook_path.chmod(0o755)
            _run(["git", "config", "core.fsmonitor", str(hook_path)], cwd=str(repo))

            selection = {"repos": [{"repoRoot": str(repo), "base": base_sha}]}
            repo_diffs.compute(str(Path(d)), selection)

            self.assertFalse(sentinel.exists(),
                              "hostile core.fsmonitor hook executed — hardened git not used")

    def test_hardened_import_present(self):
        """repo_diffs must route through discover_repos's hardened chokepoint."""
        import discover_repos
        self.assertTrue(hasattr(repo_diffs, "_git"))
        self.assertIs(repo_diffs._git, discover_repos._git)

    def test_cli_writes_repo_diffs_json(self):
        with tempfile.TemporaryDirectory() as d:
            repo = _init_repo(Path(d) / "repo")
            (repo / "a.py").write_text("x = 1\n", encoding="utf-8")
            _commit_all(repo, "init")
            base_sha = _rev_parse(repo, "HEAD")
            (repo / "a.py").write_text("x = 2\n", encoding="utf-8")
            _commit_all(repo, "edit")

            pack_dir = Path(d) / "pack"
            pack_dir.mkdir()
            selection_path = Path(d) / "selection.json"
            selection_path.write_text(json.dumps(
                {"repos": [{"repoRoot": str(repo), "base": base_sha}]}
            ), encoding="utf-8")

            script = str(Path(__file__).resolve().parent.parent / "scripts" / "repo_diffs.py")
            out = subprocess.run(
                [sys.executable, script, str(pack_dir), "--selection", str(selection_path)],
                capture_output=True, text=True,
            )
            self.assertEqual(out.returncode, 0, out.stderr)
            written = json.loads((pack_dir / "repo-diffs.json").read_text(encoding="utf-8"))
            self.assertEqual(len(written["repos"]), 1)


if __name__ == "__main__":
    unittest.main()
