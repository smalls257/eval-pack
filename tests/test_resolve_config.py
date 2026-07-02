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


class TestStanceEmbedding(unittest.TestCase):
    def test_default_stance_text_embedded(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as pack:
            r = _run([root, pack])
            self.assertEqual(r.returncode, 0, r.stderr)
            cfg = json.loads((Path(pack) / "eval-config.json").read_text())
            self.assertIn("analysisStanceText", cfg)
            self.assertIn("Skeptical Reviewer", cfg["analysisStanceText"])

    def test_unknown_stance_halts(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as pack:
            (Path(root) / ".eval-pack.json").write_text(
                json.dumps({"analysisStance": "bogus-stance"}), encoding="utf-8")
            r = _run([root, pack])
            self.assertEqual(r.returncode, 1)
            self.assertIn("analysisStance", r.stderr)
            self.assertFalse((Path(pack) / "eval-config.json").exists())


if __name__ == "__main__":
    unittest.main()


class TestUserSpaceStance(unittest.TestCase):
    def test_custom_stance_from_project_no_plugin_edit(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as pack:
            sd = Path(root) / ".eval-pack" / "stances"
            sd.mkdir(parents=True)
            (sd / "acme-auditor.md").write_text("# Acme Auditor\nBe ruthless.", encoding="utf-8")
            (Path(root) / ".eval-pack.json").write_text(
                json.dumps({"analysisStance": "acme-auditor"}), encoding="utf-8")
            r = _run([root, pack])
            self.assertEqual(r.returncode, 0, r.stderr)
            cfg = json.loads((Path(pack) / "eval-config.json").read_text())
            self.assertIn("Acme Auditor", cfg["analysisStanceText"])

    def test_project_stance_overrides_bundled_name(self):
        # a project file named like a bundled preset wins (project-first)
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as pack:
            sd = Path(root) / ".eval-pack" / "stances"
            sd.mkdir(parents=True)
            (sd / "skeptical-reviewer.md").write_text("PROJECT OVERRIDE STANCE", encoding="utf-8")
            (Path(root) / ".eval-pack.json").write_text(
                json.dumps({"analysisStance": "skeptical-reviewer"}), encoding="utf-8")
            r = _run([root, pack])
            self.assertEqual(r.returncode, 0, r.stderr)
            cfg = json.loads((Path(pack) / "eval-config.json").read_text())
            self.assertIn("PROJECT OVERRIDE STANCE", cfg["analysisStanceText"])


class TestCanNeverFailWarning(unittest.TestCase):
    def test_all_flags_disabled_warns(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as pack:
            (Path(root) / ".eval-pack.json").write_text(json.dumps({
                "flagSeverities": {k: "off" for k in
                    ["testsFailing", "testsPassing", "falseCompletions", "highRetry",
                     "scopeDrift", "partialSession", "unknownVerdict", "overBudget"]}
            }), encoding="utf-8")
            r = _run([root, pack])
            self.assertEqual(r.returncode, 0)          # warn, don't block
            self.assertIn("can never fail", r.stderr)   # but say so loudly


class TestCanNeverFailGuardCoversFailureSet(unittest.TestCase):
    def test_only_failure_flags_off_still_warns(self):
        # the N1 bypass: turning off exactly the 7 failure-capable flags (no green ids)
        import sys as _sys
        _sys.path.insert(0, str(SCRIPTS))
        import config as _config
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as pack:
            (Path(root) / ".eval-pack.json").write_text(json.dumps({
                "flagSeverities": {fid: "off" for fid in _config.FAILURE_FLAG_IDS}
            }), encoding="utf-8")
            r = _run([root, pack])
            self.assertEqual(r.returncode, 0)
            self.assertIn("can never fail", r.stderr)
