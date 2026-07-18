# tests/test_detect_patterns_config.py
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import detect_patterns  # noqa: E402


class TestScopeDriftThreshold(unittest.TestCase):
    def _metrics(self, d, files_changed):
        (Path(d) / "metrics.json").write_text(
            json.dumps({"filesChanged": files_changed}), encoding="utf-8"
        )

    def test_uses_supplied_threshold(self):
        with tempfile.TemporaryDirectory() as d:
            self._metrics(d, 6)
            self.assertTrue(detect_patterns.check_scope_drift(d, threshold=5))
            self.assertFalse(detect_patterns.check_scope_drift(d, threshold=10))


def _entry(etype, text):
    return {"type": etype, "message": {"content": [{"type": "text", "text": text}]}}


class TestConfigurableDetection(unittest.TestCase):
    def test_custom_done_pattern(self):
        entries = [_entry("assistant", "task fertig jetzt"), _entry("user", "nein, broken")]
        rx = detect_patterns.compile_patterns({"done": [r"(?i)fertig"],
                                               "correction": [r"(?i)(nein|broken)"],
                                               "retry": [r"(?i)nochmal"]})
        found = detect_patterns.detect_false_completions(entries, rx, window=1, trunc=120)
        self.assertEqual(len(found), 1)

    def test_window_extends_reach(self):
        entries = [_entry("assistant", "all done"),
                   _entry("assistant", "wrapping up"),
                   _entry("user", "no, still broken")]
        rx = detect_patterns.compile_patterns(detect_patterns.DEFAULT_PATTERNS)
        self.assertEqual(len(detect_patterns.detect_false_completions(entries, rx, window=1, trunc=120)), 0)
        self.assertEqual(len(detect_patterns.detect_false_completions(entries, rx, window=2, trunc=120)), 1)

    def test_trunc_len_applied(self):
        entries = [_entry("assistant", "done " + "x" * 300), _entry("user", "no, wrong")]
        rx = detect_patterns.compile_patterns(detect_patterns.DEFAULT_PATTERNS)
        found = detect_patterns.detect_false_completions(entries, rx, window=1, trunc=10)
        self.assertEqual(len(found[0]["agentClaim"]), 10)


class TestFlagSeverities(unittest.TestCase):
    def _run(self, cfg_extra, metrics=None, verdict=None):
        import subprocess
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d)
            (pack / "transcript.jsonl").write_text(
                json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "hi"}]}}) + "\n",
                encoding="utf-8")
            base = dict(json.loads(json.dumps(__import__("config").DEFAULTS)))
            base.update(cfg_extra)
            (pack / "eval-config.json").write_text(json.dumps(base), encoding="utf-8")
            if metrics:
                (pack / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
            if verdict:
                (pack / "test-results.json").write_text(json.dumps({"verdict": verdict}), encoding="utf-8")
            subprocess.run(
                [sys.executable, str(SCRIPTS / "detect_patterns.py"),
                 str(pack / "transcript.jsonl"), str(pack), "--config", str(pack / "eval-config.json")],
                check=True, capture_output=True, text=True)
            return json.loads((pack / "patterns.json").read_text(encoding="utf-8"))

    def test_severity_override_and_off(self):
        out = self._run({"flagSeverities": {"testsFailing": "amber"}}, verdict="fail")
        flag = next(f for f in out["flags"] if f["id"] == "testsFailing")
        self.assertEqual(flag["level"], "amber")
        out2 = self._run({"flagSeverities": {"testsFailing": "off"}}, verdict="fail")
        self.assertFalse(any(f["id"] == "testsFailing" for f in out2["flags"]))

    def test_unknown_verdict_surfaces(self):
        out = self._run({}, verdict="banana")
        self.assertTrue(any(f["id"] == "unknownVerdict" and f["level"] == "amber" for f in out["flags"]))


if __name__ == "__main__":
    unittest.main()


class TestSuppressionHonesty(unittest.TestCase):
    def test_suppressed_failure_does_not_claim_clean_pass(self):
        # N2: testsFailing off + verdict fail must NOT render "Clean first-pass"
        helper = TestFlagSeverities()
        out = helper._run({"flagSeverities": {"testsFailing": "off"}}, verdict="fail")
        self.assertFalse(any(f["id"] == "cleanPass" for f in out["flags"]))
        self.assertTrue(any(f["id"] == "flagsSuppressed" and f["level"] == "amber" for f in out["flags"]))
        self.assertEqual(out["suppressedFlags"], ["testsFailing"])


class TestCustomDetectors(unittest.TestCase):
    def _run_pack(self, detectors, lines, extra_cfg=None):
        import subprocess
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d)
            (pack / "transcript.jsonl").write_text(
                "\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
            base = dict(json.loads(json.dumps(__import__("config").DEFAULTS)))
            base["customDetectors"] = detectors
            base.update(extra_cfg or {})
            (pack / "eval-config.json").write_text(json.dumps(base), encoding="utf-8")
            subprocess.run(
                [sys.executable, str(SCRIPTS / "detect_patterns.py"),
                 str(pack / "transcript.jsonl"), str(pack), "--config", str(pack / "eval-config.json")],
                check=True, capture_output=True, text=True)
            return json.loads((pack / "patterns.json").read_text(encoding="utf-8"))

    def test_bash_scope_detector_fires(self):
        lines = [{"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Bash", "id": "b1",
             "input": {"command": "sudo rm -rf /tmp/x"}}]}}]
        out = self._run_pack([{"id": "sudoUsed", "level": "red", "label": "sudo executed",
                               "scope": "bash", "pattern": r"\bsudo\b"}], lines)
        flag = next(f for f in out["flags"] if f["id"] == "sudoUsed")
        self.assertEqual(flag["level"], "red")
        self.assertEqual(flag["count"], 1)

    def test_files_scope_and_threshold(self):
        lines = [{"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Read", "id": "r1", "input": {"file_path": "/app/.env"}}]}}]
        det = {"id": "envRead", "level": "amber", "label": ".env accessed",
               "scope": "files", "pattern": r"\.env$", "threshold": 2}
        out = self._run_pack([det], lines)
        self.assertFalse(any(f["id"] == "envRead" for f in out["flags"]))  # 1 < threshold 2
        det["threshold"] = 1
        out = self._run_pack([det], lines)
        self.assertTrue(any(f["id"] == "envRead" for f in out["flags"]))

    def test_text_scope_fires_on_assistant_text(self):
        lines = [{"type": "assistant", "message": {"content": [
            {"type": "text", "text": "I will just hardcode the API key"}]}}]
        out = self._run_pack([{"id": "hardcode", "level": "amber", "label": "hardcode mention",
                               "scope": "text", "pattern": "(?i)hardcode"}], lines)
        self.assertTrue(any(f["id"] == "hardcode" for f in out["flags"]))

    def test_user_scope_and_off_suppression(self):
        lines = [{"type": "user", "message": {"content": [
            {"type": "text", "text": "please just hardcode the key"}]}}]
        det = {"id": "userHardcode", "level": "amber", "label": "user asked to hardcode",
               "scope": "user", "pattern": "(?i)hardcode"}
        out = self._run_pack([det], lines)
        self.assertTrue(any(f["id"] == "userHardcode" for f in out["flags"]))
        # suppression via flagSeverities applies to custom ids
        out2 = self._run_pack([det], lines, extra_cfg={"flagSeverities": {"userHardcode": "off"}})
        self.assertFalse(any(f["id"] == "userHardcode" for f in out2["flags"]))
        self.assertIn("userHardcode", out2["suppressedFlags"])

    def test_green_custom_detector_replaces_cleanpass(self):
        lines = [{"type": "assistant", "message": {"content": [
            {"type": "text", "text": "policy satisfied"}]}}]
        det = {"id": "policyOk", "level": "green", "label": "policy satisfied",
               "scope": "text", "pattern": "policy satisfied"}
        out = self._run_pack([det], lines)
        self.assertTrue(any(f["id"] == "policyOk" for f in out["flags"]))
        self.assertFalse(any(f["id"] == "cleanPass" for f in out["flags"]))


class TestDetectorScripts(unittest.TestCase):
    def _run_pack(self, script_body, lines=None, extra_cfg=None):
        import subprocess
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d)
            script = pack / "det.py"
            script.write_text(script_body, encoding="utf-8")
            (pack / "transcript.jsonl").write_text(
                json.dumps(lines or {"type": "assistant", "message": {"content": "hi"}}) + "\n",
                encoding="utf-8")
            base = dict(json.loads(json.dumps(__import__("config").DEFAULTS)))
            base["detectorScripts"] = [str(script)]
            base.update(extra_cfg or {})
            (pack / "eval-config.json").write_text(json.dumps(base), encoding="utf-8")
            subprocess.run(
                [sys.executable, str(SCRIPTS / "detect_patterns.py"),
                 str(pack / "transcript.jsonl"), str(pack), "--config", str(pack / "eval-config.json")],
                check=True, capture_output=True, text=True)
            return json.loads((pack / "patterns.json").read_text(encoding="utf-8"))

    def test_script_flags_merged(self):
        out = self._run_pack(
            'import json; print(json.dumps({"flags": ['
            '{"id": "prodTouch", "level": "red", "label": "prod path modified"}]}))')
        flag = next(f for f in out["flags"] if f["id"] == "prodTouch")
        self.assertEqual(flag["level"], "red")

    def test_failing_script_becomes_red_flag(self):
        out = self._run_pack('raise SystemExit(3)')
        self.assertTrue(any(f["id"] == "detectorFailed" and f["level"] == "red"
                            for f in out["flags"]))

    def test_malformed_output_becomes_red_flag(self):
        out = self._run_pack('print("not json")')
        self.assertTrue(any(f["id"] == "detectorFailed" for f in out["flags"]))

    def test_bad_level_in_script_output_rejected(self):
        out = self._run_pack(
            'import json; print(json.dumps({"flags": [{"id": "x", "level": "purple", "label": "l"}]}))')
        self.assertFalse(any(f["id"] == "x" for f in out["flags"]))
        self.assertTrue(any(f["id"] == "detectorFailed" for f in out["flags"]))

    def test_detectorfailed_not_suppressible(self):
        out = self._run_pack('raise SystemExit(3)',
                             extra_cfg={"flagSeverities": {"detectorFailed": "off"}})
        self.assertTrue(any(f["id"] == "detectorFailed" for f in out["flags"]))

    def test_script_flag_counterfeiting_builtin_rejected(self):
        out = self._run_pack(
            'import json; print(json.dumps({"flags": ['
            '{"id": "testsPassing", "level": "green", "label": "fake pass"}]}))')
        self.assertFalse(any(f["id"] == "testsPassing" for f in out["flags"]))
        self.assertTrue(any(f["id"] == "detectorFailed" for f in out["flags"]))


class TestSuppressedRedVisibility(unittest.TestCase):
    def test_suppressed_red_with_surviving_flags_is_noted(self):
        # final-review finding: red suppression must not silently downgrade the banner
        helper = TestFlagSeverities()
        # verdict fail (red, suppressed) + scope drift (amber, survives)
        out = helper._run({"flagSeverities": {"testsFailing": "off"},
                           "scopeDriftFileThreshold": 1},
                          metrics={"filesChanged": 5, "totalTokens": 1}, verdict="fail")
        self.assertTrue(any(f["id"] == "scopeDrift" for f in out["flags"]))
        note = next(f for f in out["flags"] if f["id"] == "flagsSuppressed")
        self.assertEqual(note["level"], "amber")
        self.assertIn("testsFailing", note["label"])

    def test_suppressed_amber_with_surviving_flags_no_note(self):
        # only RED suppression forces the note when other flags survive
        helper = TestFlagSeverities()
        out = helper._run({"flagSeverities": {"scopeDrift": "off"},
                           "scopeDriftFileThreshold": 1},
                          metrics={"filesChanged": 5, "totalTokens": 1}, verdict="fail")
        self.assertTrue(any(f["id"] == "testsFailing" for f in out["flags"]))
        self.assertFalse(any(f["id"] == "flagsSuppressed" for f in out["flags"]))
