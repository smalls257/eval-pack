import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import extract_metrics  # noqa: E402


def _agent_call(tool_id, model):
    return {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Agent", "id": tool_id,
         "input": {"model": model, "description": "do work"}},
    ]}}


def _agent_result(tool_id, usage_text):
    return {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": tool_id, "content": usage_text},
    ]}}


class SubagentTokenTests(unittest.TestCase):
    def test_parses_subagent_tokens_field(self):
        # The real Agent tool_result usage field is `subagent_tokens`, not total_tokens.
        entries = [
            _agent_call("t1", "claude-opus-4-8"),
            _agent_result("t1", "agent done\n<usage>subagent_tokens: 33018\n"
                                "tool_uses: 7\nduration_ms: 48566</usage>"),
        ]
        total, by_model = extract_metrics.extract_subagent_tokens(entries)
        self.assertEqual(total, 33018)
        self.assertEqual(by_model, [{"model": "claude-opus-4-8", "totalTokens": 33018}])

    def test_still_parses_total_tokens_fallback(self):
        # Older/other format may report total_tokens — keep it working.
        entries = [
            _agent_call("t1", "claude-x"),
            _agent_result("t1", "<usage>total_tokens: 500</usage>"),
        ]
        total, _ = extract_metrics.extract_subagent_tokens(entries)
        self.assertEqual(total, 500)

    def test_sums_across_multiple_subagents(self):
        entries = [
            _agent_call("t1", "m"), _agent_result("t1", "subagent_tokens: 100"),
            _agent_call("t2", "m"), _agent_result("t2", "subagent_tokens: 250"),
        ]
        total, by_model = extract_metrics.extract_subagent_tokens(entries)
        self.assertEqual(total, 350)
        self.assertEqual(by_model, [{"model": "m", "totalTokens": 350}])

    def test_non_agent_tool_results_ignored(self):
        entries = [
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "bash1",
                 "content": "subagent_tokens: 999"}]}},
        ]
        total, _ = extract_metrics.extract_subagent_tokens(entries)
        self.assertEqual(total, 0)


class SyntheticModelTests(unittest.TestCase):
    def _run(self, entries):
        with tempfile.TemporaryDirectory() as d:
            tr = Path(d) / "t.jsonl"
            tr.write_text("\n".join(json.dumps(e) for e in entries) + "\n",
                          encoding="utf-8")
            subprocess.run(
                [sys.executable, str(SCRIPTS / "extract_metrics.py"),
                 str(tr), str(d)],
                check=True, capture_output=True, text=True)
            return json.loads((Path(d) / "metrics.json").read_text())

    def test_synthetic_excluded_from_per_model_and_lastmodel(self):
        m = self._run([
            {"type": "assistant", "message": {
                "model": "claude-opus-4-8",
                "usage": {"input_tokens": 100, "output_tokens": 50},
                "content": [{"type": "text", "text": "real"}]}},
            {"type": "assistant", "message": {
                "model": "<synthetic>",
                "usage": {"input_tokens": 0, "output_tokens": 0},
                "content": [{"type": "text", "text": "No response requested."}]}},
        ])
        models = [r["model"] for r in m["tokensByModel"]]
        self.assertEqual(models, ["claude-opus-4-8"])  # no <synthetic> row
        self.assertEqual(m["lastModel"], "claude-opus-4-8")  # not the placeholder


if __name__ == "__main__":
    unittest.main()
