# tests/test_config.py
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import config  # noqa: E402


def _write(d, name, obj):
    (Path(d) / name).write_text(json.dumps(obj), encoding="utf-8")


class TestLoadConfig(unittest.TestCase):
    def test_defaults_when_no_files(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = config.load_config(d, env={})
            self.assertEqual(cfg["scopeDriftFileThreshold"], 10)
            self.assertEqual(cfg["retryAmberThreshold"], 4)
            self.assertEqual(cfg["skillArgsMaxLen"], 200)

    def test_returned_lists_do_not_alias_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = config.load_config(d, env={})
            cfg["frictionCategories"].append("mutated")
            self.assertNotIn("mutated", config.DEFAULTS["frictionCategories"])

    def test_project_overrides_scalar(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, ".eval-pack.json", {"scopeDriftFileThreshold": 5})
            cfg = config.load_config(d, env={})
            self.assertEqual(cfg["scopeDriftFileThreshold"], 5)

    def test_local_overrides_project(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, ".eval-pack.json", {"scopeDriftFileThreshold": 5})
            _write(d, ".eval-pack.local.json", {"scopeDriftFileThreshold": 7})
            cfg = config.load_config(d, env={})
            self.assertEqual(cfg["scopeDriftFileThreshold"], 7)

    def test_list_concat_dedupe(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, ".eval-pack.json", {"frictionCategories": ["security", "tooling"]})
            cfg = config.load_config(d, env={})
            # defaults + new, "tooling" not duplicated
            self.assertEqual(
                cfg["frictionCategories"],
                ["tooling", "structure", "naming", "docs", "other", "security"],
            )

    def test_env_overrides_everything(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, ".eval-pack.json", {"scopeDriftFileThreshold": 5})
            cfg = config.load_config(d, env={"CLAUDE_PLUGIN_OPTION_scopeDriftFileThreshold": "3"})
            self.assertEqual(cfg["scopeDriftFileThreshold"], 3)

    def test_extends_lower_priority_than_project(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "base.json", {"scopeDriftFileThreshold": 5, "retryAmberThreshold": 2})
            _write(d, ".eval-pack.json", {"extends": ["base.json"], "scopeDriftFileThreshold": 9})
            cfg = config.load_config(d, env={})
            self.assertEqual(cfg["scopeDriftFileThreshold"], 9)   # project wins
            self.assertEqual(cfg["retryAmberThreshold"], 2)       # preset-only key kept


class TestValidate(unittest.TestCase):
    def test_ok_for_defaults(self):
        self.assertEqual(config.validate(dict(config.DEFAULTS)), [])

    def test_unknown_key(self):
        errs = config.validate({"frobnicate": 1})
        self.assertTrue(any("unknown config key" in e for e in errs))

    def test_type_error(self):
        errs = config.validate({"scopeDriftFileThreshold": "ten"})
        self.assertTrue(any("scopeDriftFileThreshold" in e for e in errs))

    def test_bool_rejected_for_int(self):
        errs = config.validate({"retryAmberThreshold": True})
        self.assertTrue(any("retryAmberThreshold" in e and "bool" in e for e in errs))


if __name__ == "__main__":
    unittest.main()
