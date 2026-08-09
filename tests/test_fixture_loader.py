import subprocess, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import fixture_loader  # noqa: E402

class TestFixtureLoader(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
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

if __name__ == "__main__":
    unittest.main()
