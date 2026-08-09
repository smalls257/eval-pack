import os, subprocess, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import fixture_loader  # noqa: E402

class TestFixtureLoader(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))

    def test_transcript_only_fixture(self):
        (self.tmp / "transcript.jsonl").write_text('{"type":"user"}\n')
        with fixture_loader.load_fixture(self.tmp) as (pack, repo, base):
            self.assertEqual(pack, self.tmp)
            self.assertIsNone(repo)
            self.assertIsNone(base)

    def test_diff_fixture_reconstructs_patch(self):
        base = self.tmp / "base"; base.mkdir()
        (base / "a.txt").write_text("hello\n")
        patch = ("diff --git a/a.txt b/a.txt\n--- a/a.txt\n+++ b/a.txt\n"
                 "@@ -1 +1 @@\n-hello\n+hello world\n")
        (self.tmp / "delivered.patch").write_text(patch)
        (self.tmp / "transcript.jsonl").write_text('{"type":"user"}\n')
        with fixture_loader.load_fixture(self.tmp) as (pack, repo, diff_base):
            self.assertIsNotNone(repo)
            self.assertTrue(diff_base)
            out = subprocess.run(["git", "-C", str(repo), "diff", diff_base],
                                 capture_output=True, text=True, check=True).stdout
            self.assertIn("hello world", out)

    def test_diff_fixture_reconstructs_patch_from_relative_path(self):
        base = self.tmp / "base"; base.mkdir()
        (base / "a.txt").write_text("hello\n")
        patch = ("diff --git a/a.txt b/a.txt\n--- a/a.txt\n+++ b/a.txt\n"
                 "@@ -1 +1 @@\n-hello\n+hello world\n")
        (self.tmp / "delivered.patch").write_text(patch)
        (self.tmp / "transcript.jsonl").write_text('{"type":"user"}\n')

        # A relative path only exists when tmp and cwd share a drive. On Windows CI the system
        # temp dir (C:) and the checkout (D:) are on different mounts, so os.path.relpath raises —
        # there is nothing to test there, so skip rather than fail.
        try:
            relative_fixture_dir = Path(os.path.relpath(self.tmp))
        except ValueError:
            self.skipTest("temp dir and cwd are on different drives; no relative path to exercise")
        with fixture_loader.load_fixture(relative_fixture_dir) as (pack, repo, diff_base):
            self.assertIsNotNone(repo)
            self.assertTrue(diff_base)
            out = subprocess.run(["git", "-C", str(repo), "diff", diff_base],
                                 capture_output=True, text=True, check=True).stdout
            self.assertIn("hello world", out)

if __name__ == "__main__":
    unittest.main()
