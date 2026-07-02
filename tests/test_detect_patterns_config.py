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

    def test_cost_budget_flag(self):
        out = self._run({"costBudgetTokens": 100}, metrics={"totalTokens": 500, "filesChanged": 0})
        self.assertTrue(any(f["id"] == "overBudget" for f in out["flags"]))


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
