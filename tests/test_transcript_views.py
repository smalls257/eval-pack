import json
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
WITH_TRANSPORT_METADATA = {
    "turnId": 4, "type": "assistant", "timestamp": "2026-08-15T00:00:00Z",
    "uuid": "u-1", "cwd": "/home/x", "toolUseResult": {"stdout": "huge" * 1000},
    "message": {"role": "assistant", "content": [{"type": "text", "text": "hi"}]},
}


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


def test_conversation_strips_non_essential_top_level_fields():
    out = tv.project_record(WITH_TRANSPORT_METADATA, "conversation", 400)
    assert "toolUseResult" not in out
    assert "uuid" not in out
    assert "cwd" not in out
    assert out["turnId"] == 4
    assert out["type"] == "assistant"
    assert out["timestamp"] == "2026-08-15T00:00:00Z"
    assert out["message"]["content"][0]["type"] == "text"


def test_activity_strips_non_essential_top_level_fields():
    out = tv.project_record(WITH_TRANSPORT_METADATA, "activity", 400)
    assert "toolUseResult" not in out
    assert "uuid" not in out
    assert "cwd" not in out
    assert out["turnId"] == 4
    assert out["type"] == "assistant"
    assert out["timestamp"] == "2026-08-15T00:00:00Z"


def test_full_view_keeps_top_level_fields_unchanged():
    out = tv.project_record(WITH_TRANSPORT_METADATA, "full", 400)
    assert out == WITH_TRANSPORT_METADATA
    assert out is WITH_TRANSPORT_METADATA


def _emit_records():
    return [
        {"turnId": 0, "type": "user", "message": {"role": "user", "content": [{"type": "text", "text": "hi"}]}},
        {"turnId": 1, "type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "content": "Z" * 900}]}},
        {"turnId": 2, "type": "file-history-snapshot", "message": {}},
    ]


def test_emit_writes_header_then_records(tmp_path):
    paths = tv.emit_views(_emit_records(), ["conversation"], tmp_path, 400, "abc123")
    lines = paths["conversation"].read_text().splitlines()
    header = json.loads(lines[0])
    assert header["_view"] == "conversation"
    assert header["_viewVersion"] == tv.VIEW_VERSION
    assert header["_sourceTranscriptSha256"] == "abc123"
    # tool_result record + noise record dropped -> counts recorded
    assert header["_dropped"]["file-history-snapshot"] == 1
    assert header["_dropped"]["tool_result"] == 1  # a whole record dropped for having only tool_result
    body = [json.loads(x) for x in lines[1:]]
    assert [r["turnId"] for r in body] == [0]


def test_emit_activity_records_truncation_count(tmp_path):
    paths = tv.emit_views(_emit_records(), ["activity"], tmp_path, 400, "abc123")
    header = json.loads(paths["activity"].read_text().splitlines()[0])
    assert header["_truncated"] == {"toolResultTruncLen": 400, "count": 1}


def test_emit_header_records_kept_top_level_fields_for_non_full_view(tmp_path):
    paths = tv.emit_views(_emit_records(), ["conversation"], tmp_path, 400, "abc123")
    header = json.loads(paths["conversation"].read_text().splitlines()[0])
    assert header["_keptTopLevelFields"] == ["turnId", "type", "message", "timestamp"]
