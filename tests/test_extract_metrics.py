import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
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


if __name__ == "__main__":
    unittest.main()
