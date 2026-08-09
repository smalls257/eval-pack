import json, shutil, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import build_bundle  # noqa: E402

class TestBuildBundle(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

    def test_transcript_only_fixture(self):
        lines = [{"type": "user", "message": {"role": "user", "content": "hi"}}]
        build_bundle.write_fixture(self.tmp / "c1", lines, {"source": "x", "license": "MIT"})
        got = (self.tmp / "c1" / "transcript.jsonl").read_text().splitlines()
        self.assertEqual(json.loads(got[0])["message"]["content"], "hi")
        self.assertEqual(json.loads((self.tmp / "c1" / "meta.json").read_text())["license"], "MIT")
        self.assertFalse((self.tmp / "c1" / "base").exists())

    def test_diff_fixture(self):
        lines = [{"type": "user", "message": {"role": "user", "content": "hi"}}]
        build_bundle.write_fixture(self.tmp / "c2", lines, {"source": "x"},
                                   base_files={"pkg/a.py": "hello\n"}, delivered_patch="PATCH\n")
        self.assertEqual((self.tmp / "c2" / "base" / "pkg" / "a.py").read_text(), "hello\n")
        self.assertEqual((self.tmp / "c2" / "delivered.patch").read_text(), "PATCH\n")

if __name__ == "__main__":
    unittest.main()
