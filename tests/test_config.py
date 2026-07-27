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


class TestLensKeys(unittest.TestCase):
    def test_new_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = config.load_config(d, env={})
            lenses = {lens["skill"]: lens for lens in cfg["analysisLenses"]}
            self.assertEqual(len(cfg["analysisLenses"]), 7)
            self.assertEqual(lenses["review"], {"skill": "review", "role": "contributor"})
            self.assertEqual(lenses["business-risk"], {"skill": "business-risk", "role": "contributor"})
            self.assertEqual(lenses["friction"], {"skill": "friction", "role": "contributor"})
            self.assertEqual(lenses["repo-improvements"], {"skill": "repo-improvements", "role": "contributor"})
            self.assertEqual(lenses["user-improvements"], {"skill": "user-improvements", "role": "contributor"})
            self.assertEqual(lenses["requirement-drift"], {"skill": "requirement-drift", "role": "scorer"})
            self.assertEqual(lenses["verification-rigor"], {"skill": "verification-rigor", "role": "scorer"})
            self.assertEqual(cfg["verdictAggregation"], "core")

    def test_unknown_aggregation_rejected(self):
        errs = config.validate({"verdictAggregation": "sneaky"})
        self.assertTrue(any("verdictAggregation" in e for e in errs))

    def test_known_aggregation_accepted(self):
        self.assertEqual(config.validate({"verdictAggregation": "min"}), [])

    def test_lens_must_have_skill_and_valid_role(self):
        errs = config.validate({"analysisLenses": [{"skill": "x", "role": "contributor"}]})
        self.assertEqual(errs, [])
        bad_role = config.validate({"analysisLenses": [{"skill": "x", "role": "boss"}]})
        self.assertTrue(any("analysisLenses" in e for e in bad_role))
        no_skill = config.validate({"analysisLenses": [{"role": "scorer"}]})
        self.assertTrue(any("analysisLenses" in e for e in no_skill))

    def test_lens_template_must_be_string(self):
        errs = config.validate({"analysisLenses": [
            {"skill": "x", "role": "scorer", "template": 7}]})
        self.assertTrue(any("template" in e for e in errs))
        self.assertEqual(config.validate({"analysisLenses": [
            {"skill": "x", "role": "scorer", "template": "t.html"}]}), [])


class TestCosmeticKeys(unittest.TestCase):
    def test_new_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = config.load_config(d, env={})
            self.assertEqual(cfg["brandName"], "Eval Pack")
            self.assertEqual(cfg["reportTitle"], "")
            self.assertEqual(cfg["footerText"], "")
            self.assertEqual(cfg["subjectNoun"], "extension")
            self.assertEqual(cfg["defaultTheme"], "dark")
            self.assertEqual(cfg["sections"], [])
            self.assertEqual(cfg["zipNameTemplate"], "")
            self.assertEqual(cfg["repoBaseUrl"], "")
            self.assertEqual(cfg["messages"], {})

    def test_theme_must_be_known(self):
        errs = config.validate({"defaultTheme": "neon"})
        self.assertTrue(any("defaultTheme" in e for e in errs))

    def test_theme_known_accepted(self):
        self.assertEqual(config.validate({"defaultTheme": "light"}), [])

    def test_brand_override(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ".eval-pack.json").write_text(
                json.dumps({"brandName": "Acme Reports"}), encoding="utf-8")
            cfg = config.load_config(d, env={})
            self.assertEqual(cfg["brandName"], "Acme Reports")


class TestFailLoudRegressions(unittest.TestCase):
    def test_missing_extends_preset_raises(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, ".eval-pack.json", {"extends": ["nope.json"]})
            with self.assertRaises(config.ConfigError) as ctx:
                config.load_config(d, env={})
            self.assertIn("nope.json", str(ctx.exception))

    def test_garbage_bool_env_raises(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(config.ConfigError) as ctx:
                config.load_config(d, env={"CLAUDE_PLUGIN_OPTION_publishOpenable": "banana"})
            self.assertIn("publishOpenable", str(ctx.exception))

    def test_explicit_false_bool_env(self):
        with tempfile.TemporaryDirectory() as d:
            for token in ("false", "FALSE", "0", "no", "off"):
                cfg = config.load_config(d, env={"CLAUDE_PLUGIN_OPTION_publishOpenable": token})
                self.assertIs(cfg["publishOpenable"], False, token)


class TestResolveTimeGates(unittest.TestCase):
    def test_rubric_values_must_be_strings(self):
        errs = config.validate({"rubric": {"high": 42}})
        self.assertTrue(any("rubric" in e for e in errs))
        self.assertEqual(config.validate({"rubric": {"high": "no bugs"}}), [])

    def test_extends_in_local_raises(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "base.json", {"retryAmberThreshold": 2})
            _write(d, ".eval-pack.local.json", {"extends": ["base.json"]})
            with self.assertRaises(config.ConfigError) as ctx:
                config.load_config(d, env={})
            self.assertIn("local", str(ctx.exception))

    def test_env_dict_raises_clearly(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(config.ConfigError) as ctx:
                config.load_config(d, env={"CLAUDE_PLUGIN_OPTION_rubric": "high=good"})
            self.assertIn("JSON", str(ctx.exception))

    def test_env_json_array_and_object_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = config.load_config(d, env={
                "CLAUDE_PLUGIN_OPTION_redaction": '["secret{1,3}"]',
                "CLAUDE_PLUGIN_OPTION_rubric": '{"high": "ship"}',
            })
            self.assertEqual(cfg["redaction"], ["secret{1,3}"])  # comma survives (JSON, not split)
            self.assertEqual(cfg["rubric"], {"high": "ship"})

    def test_redaction_env_comma_shorthand_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(config.ConfigError) as ctx:
                config.load_config(d, env={"CLAUDE_PLUGIN_OPTION_redaction": "secret{1,3}"})
            self.assertIn("JSON array", str(ctx.exception))

    def test_env_json_list_deduped(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = config.load_config(d, env={"CLAUDE_PLUGIN_OPTION_frictionCategories": '["a","a","b"]'})
            self.assertEqual(cfg["frictionCategories"], ["a", "b"])


class TestUnifiedKeys(unittest.TestCase):
    def test_new_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = config.load_config(d, env={})
            self.assertEqual(cfg["outputDir"], ".eval-packs")
            self.assertIs(cfg["analysis"], True)
            self.assertIs(cfg["includeTranscript"], True)
            self.assertEqual(cfg["ticketBaseUrl"], "")

    def test_legacy_env_layer_still_wins(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = config.load_config(d, env={"CLAUDE_PLUGIN_OPTION_includeTranscript": "false"})
            self.assertIs(cfg["includeTranscript"], False)


if __name__ == "__main__":
    unittest.main()


class TestSkillArgsMaxLenBound(unittest.TestCase):
    def test_negative_rejected(self):
        errs = config.validate({"skillArgsMaxLen": -1})
        self.assertTrue(any("skillArgsMaxLen" in e for e in errs))

    def test_env_list_deduped(self):
        import tempfile as _t
        with _t.TemporaryDirectory() as d:
            cfg = config.load_config(d, env={"CLAUDE_PLUGIN_OPTION_frictionCategories": "a,,b,a"})
            self.assertEqual(cfg["frictionCategories"], ["a", "b"])


class TestExtendsConfinement(unittest.TestCase):
    def test_parent_escape_rejected(self):
        with tempfile.TemporaryDirectory() as outer:
            (Path(outer) / "evil.json").write_text('{"retryAmberThreshold": 7}', encoding="utf-8")
            repo = Path(outer) / "repo"
            repo.mkdir()
            _write(str(repo), ".eval-pack.json", {"extends": ["../evil.json"]})
            with self.assertRaises(config.ConfigError) as ctx:
                config.load_config(str(repo), env={})
            self.assertIn("outside the repo", str(ctx.exception))

    def test_in_repo_preset_ok(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "base.json", {"retryAmberThreshold": 2})
            _write(d, ".eval-pack.json", {"extends": ["base.json"]})
            self.assertEqual(config.load_config(d, env={})["retryAmberThreshold"], 2)


class TestDetectionCostKeys(unittest.TestCase):
    def test_new_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = config.load_config(d, env={})
            self.assertEqual(cfg["templateDir"], "")
            self.assertEqual(cfg["falseCompletionWindow"], 1)
            self.assertEqual(cfg["claimTruncLen"], 120)
            self.assertEqual(cfg["flagSeverities"], {})
            self.assertIn("done", cfg["detectionPatterns"])
            self.assertIn("correction", cfg["detectionPatterns"])
            self.assertIn("retry", cfg["detectionPatterns"])

    def test_detection_pattern_bad_regex_rejected(self):
        errs = config.validate({"detectionPatterns": {"done": ["("]}})
        self.assertTrue(any("detectionPatterns" in e for e in errs))

    def test_flag_severity_enum(self):
        self.assertEqual(config.validate({"flagSeverities": {"highRetry": "red"}}), [])
        errs = config.validate({"flagSeverities": {"highRetry": "purple"}})
        self.assertTrue(any("flagSeverities" in e for e in errs))


class TestListReplaceSentinel(unittest.TestCase):
    def test_replace_sentinel_replaces_instead_of_concat(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, ".eval-pack.json",
                   {"frictionCategories": ["!replace", "ci-flake", "review-latency"]})
            cfg = config.load_config(d, env={})
            self.assertEqual(cfg["frictionCategories"], ["ci-flake", "review-latency"])

    def test_without_sentinel_still_concats(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, ".eval-pack.json", {"frictionCategories": ["ci-flake"]})
            cfg = config.load_config(d, env={})
            self.assertEqual(cfg["frictionCategories"],
                             ["tooling", "structure", "naming", "docs", "other", "ci-flake"])

    def test_sentinel_works_across_layers(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, ".eval-pack.json", {"frictionCategories": ["ci-flake"]})
            _write(d, ".eval-pack.local.json", {"frictionCategories": ["!replace", "mine"]})
            cfg = config.load_config(d, env={})
            self.assertEqual(cfg["frictionCategories"], ["mine"])

    def test_env_json_list_sentinel_stripped(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = config.load_config(
                d, env={"CLAUDE_PLUGIN_OPTION_frictionCategories": '["!replace", "x"]'})
            self.assertEqual(cfg["frictionCategories"], ["x"])

    def test_resolved_list_with_literal_sentinel_rejected(self):
        errs = config.validate({"frictionCategories": ["a", "!replace", "b"]})
        self.assertTrue(any("!replace" in e for e in errs))

    def test_env_comma_shorthand_sentinel_rejected_loudly(self):
        # deliberate design: shorthand can't carry the sentinel — validate rejects, never guesses
        with tempfile.TemporaryDirectory() as d:
            cfg = config.load_config(
                d, env={"CLAUDE_PLUGIN_OPTION_frictionCategories": "!replace,x"})
            errs = config.validate(cfg)
            self.assertTrue(any("!replace" in e for e in errs))


class TestCustomDetectorValidation(unittest.TestCase):
    def test_valid_detector_ok(self):
        self.assertEqual(config.validate({"customDetectors": [
            {"id": "sudoUsed", "level": "red", "label": "sudo executed",
             "scope": "bash", "pattern": r"\bsudo\b"}]}), [])

    def test_bad_scope_level_pattern_rejected(self):
        for bad in (
            {"id": "x", "level": "red", "label": "l", "scope": "nope", "pattern": "a"},
            {"id": "x", "level": "purple", "label": "l", "scope": "bash", "pattern": "a"},
            {"id": "x", "level": "red", "label": "l", "scope": "bash", "pattern": "("},
            {"level": "red", "label": "l", "scope": "bash", "pattern": "a"},  # no id
        ):
            errs = config.validate({"customDetectors": [bad]})
            self.assertTrue(any("customDetectors" in e for e in errs), bad)

    def test_builtin_collision_and_duplicate_rejected(self):
        det = {"id": "testsFailing", "level": "red", "label": "l", "scope": "bash", "pattern": "a"}
        errs = config.validate({"customDetectors": [det]})
        self.assertTrue(any("collides" in e for e in errs))
        d1 = {"id": "mine", "level": "red", "label": "l", "scope": "bash", "pattern": "a"}
        errs = config.validate({"customDetectors": [d1, dict(d1)]})
        self.assertTrue(any("duplicate" in e for e in errs))


class TestSentinelInDictValues(unittest.TestCase):
    def test_sentinel_inside_detectionpatterns_rejected(self):
        # the README truth-audit footgun: dict values replace wholesale; the list
        # sentinel inside them would compile as literal regex text
        errs = config.validate({"detectionPatterns": {"done": ["!replace", "fertig"]}})
        self.assertTrue(any("detectionPatterns.done" in e and "wholesale" in e for e in errs))

    def test_clean_detectionpatterns_ok(self):
        errs = config.validate({"detectionPatterns": {"done": ["(?i)fertig"]}})
        self.assertEqual([e for e in errs if "detectionPatterns" in e], [])
