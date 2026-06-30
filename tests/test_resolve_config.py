# tests/test_resolve_config.py
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _run(args):
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "resolve_config.py"), *args],
        capture_output=True, text=True,
    )


class TestResolveConfig(unittest.TestCase):
    def test_writes_eval_config(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as pack:
            (Path(root) / ".eval-pack.json").write_text(
                json.dumps({"scopeDriftFileThreshold": 5}), encoding="utf-8"
            )
            r = _run([root, pack])
            self.assertEqual(r.returncode, 0, r.stderr)
            written = json.loads((Path(pack) / "eval-config.json").read_text())
            self.assertEqual(written["scopeDriftFileThreshold"], 5)

    def test_check_mode_valid(self):
        with tempfile.TemporaryDirectory() as root:
            r = _run([root, "--check"])
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_hard_error_unknown_key_nonzero_and_no_file(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as pack:
            (Path(root) / ".eval-pack.json").write_text(
                json.dumps({"frobnicate": 1}), encoding="utf-8"
            )
            r = _run([root, pack])
            self.assertEqual(r.returncode, 1)
            self.assertIn("unknown config key", r.stderr)
            self.assertFalse((Path(pack) / "eval-config.json").exists())

    def test_malformed_json_nonzero_and_no_file(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as pack:
            (Path(root) / ".eval-pack.json").write_text("{not json", encoding="utf-8")
            r = _run([root, pack])
            self.assertEqual(r.returncode, 1)
            self.assertIn(".eval-pack.json", r.stderr)
            self.assertFalse((Path(pack) / "eval-config.json").exists())


if __name__ == "__main__":
    unittest.main()
