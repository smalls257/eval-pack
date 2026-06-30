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


class TestMalformedInput(unittest.TestCase):
    def test_bad_int_env_raises_configerror_naming_key(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(config.ConfigError) as ctx:
                config.load_config(d, env={"CLAUDE_PLUGIN_OPTION_scopeDriftFileThreshold": "true"})
            self.assertIn("scopeDriftFileThreshold", str(ctx.exception))

    def test_malformed_json_raises_configerror_naming_file(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ".eval-pack.json").write_text("{not json", encoding="utf-8")
            with self.assertRaises(config.ConfigError) as ctx:
                config.load_config(d, env={})
            self.assertIn(".eval-pack.json", str(ctx.exception))

    def test_env_list_override_replaces(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = config.load_config(d, env={"CLAUDE_PLUGIN_OPTION_frictionCategories": "a,b,c"})
            self.assertEqual(cfg["frictionCategories"], ["a", "b", "c"])


class TestResolveRoundTrip(unittest.TestCase):
    def test_resolved_config_strips_meta_and_validates(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "base.json", {"retryAmberThreshold": 2})
            _write(d, ".eval-pack.json",
                   {"extends": ["base.json"], "$schema": "x", "scopeDriftFileThreshold": 9})
            cfg = config.load_config(d, env={})
            self.assertNotIn("extends", cfg)
            self.assertNotIn("$schema", cfg)
            self.assertEqual(config.validate(cfg), [])


class TestReadConfig(unittest.TestCase):
    def test_read_config_from_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "eval-config.json"
            p.write_text(json.dumps({"scopeDriftFileThreshold": 42}), encoding="utf-8")
            self.assertEqual(config.read_config(str(p))["scopeDriftFileThreshold"], 42)


class TestRedactionKeys(unittest.TestCase):
    def test_new_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = config.load_config(d, env={})
            self.assertEqual(cfg["redaction"], [])
            self.assertEqual(cfg["publishOpenable"], True)
            self.assertEqual(cfg["openableDir"], "")

    def test_bool_env_coercion_false(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = config.load_config(d, env={"CLAUDE_PLUGIN_OPTION_publishOpenable": "false"})
            self.assertIs(cfg["publishOpenable"], False)

    def test_bool_env_coercion_true(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = config.load_config(d, env={"CLAUDE_PLUGIN_OPTION_publishOpenable": "1"})
            self.assertIs(cfg["publishOpenable"], True)

    def test_redaction_list_validates(self):
        self.assertEqual(config.validate({"redaction": ["sk-[0-9]+"]}), [])

    def test_publishopenable_must_be_bool(self):
        errs = config.validate({"publishOpenable": "yes"})
        self.assertTrue(any("publishOpenable" in e for e in errs))


class TestPromptRubricKeys(unittest.TestCase):
    def test_new_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = config.load_config(d, env={})
            self.assertEqual(cfg["analysisStance"], "skeptical-reviewer")
            self.assertEqual(cfg["rubric"], {})
            self.assertEqual(cfg["retrospectiveQuestions"], [])
            self.assertEqual(cfg["evaluatorPromptFile"], "")

    def test_rubric_dict_validates(self):
        self.assertEqual(config.validate({"rubric": {"high": "no bugs"}}), [])

    def test_rubric_must_be_object(self):
        errs = config.validate({"rubric": ["not", "a", "dict"]})
        self.assertTrue(any("rubric" in e for e in errs))

    def test_stance_override(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ".eval-pack.json").write_text(
                json.dumps({"analysisStance": "collaborative-coach"}), encoding="utf-8")
            cfg = config.load_config(d, env={})
            self.assertEqual(cfg["analysisStance"], "collaborative-coach")

    def test_returned_dicts_do_not_alias_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = config.load_config(d, env={})
            cfg["rubric"]["mutated"] = True
            self.assertNotIn("mutated", config.DEFAULTS["rubric"])


if __name__ == "__main__":
    unittest.main()
