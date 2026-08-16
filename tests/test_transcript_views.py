import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import transcript_views as tv  # noqa: E402

ASSISTANT = {"turnId": 1, "type": "assistant",
             "message": {"role": "assistant", "content": [
                 {"type": "thinking", "thinking": "hmm"},
                 {"type": "text", "text": "hello"},
                 {"type": "tool_use", "name": "Bash", "input": {"command": "pytest"}}]}}
TOOL_RESULT = {"turnId": 2, "type": "user",
               "message": {"role": "user", "content": [
                   {"type": "tool_result", "content": "X" * 5000}]}}
NOISE = {"turnId": 3, "type": "file-history-snapshot", "message": {}}


def test_full_is_identity():
    assert tv.project_record(ASSISTANT, "full", 400) == ASSISTANT


def test_conversation_keeps_text_and_thinking_drops_tools():
    out = tv.project_record(ASSISTANT, "conversation", 400)
    kinds = [b["type"] for b in out["message"]["content"]]
    assert kinds == ["thinking", "text"]  # tool_use removed
    assert out["turnId"] == 1


def test_conversation_drops_tool_result_record():
    assert tv.project_record(TOOL_RESULT, "conversation", 400) is None


def test_conversation_drops_structural_noise():
    assert tv.project_record(NOISE, "conversation", 400) is None


def test_activity_keeps_tool_use_and_truncates_tool_result():
    au = tv.project_record(ASSISTANT, "activity", 400)
    assert [b["type"] for b in au["message"]["content"]] == ["thinking", "text", "tool_use"]
    tr = tv.project_record(TOOL_RESULT, "activity", 400)
    block = tr["message"]["content"][0]
    assert block["type"] == "tool_result"
    assert len(block["content"]) < 5000
    assert block.get("_truncated") is True


def test_activity_drops_structural_noise():
    assert tv.project_record(NOISE, "activity", 400) is None


def test_unknown_view_raises():
    with pytest.raises(ValueError):
        tv.project_record(ASSISTANT, "bogus", 400)
