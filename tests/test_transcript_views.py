import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

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

ASSIST_FULL = {"turnId": 5, "type": "assistant", "toolUseResult": {"x": "y"},
    "message": {"role": "assistant", "content": [
        {"type": "thinking", "thinking": "planning"},
        {"type": "text", "text": "Running the tests now."},
        {"type": "tool_use", "name": "Bash", "input": {"command": "pytest tests/ -q", "description": "run tests"}}]}}
RESULT_REC = {"turnId": 6, "type": "user",
    "message": {"role": "user", "content": [
        {"type": "tool_result", "content": "collecting...\n" + "x"*5000 + "\n3 passed in 1.2s", "is_error": False}]}}
THINKING_ONLY = {"turnId": 7, "type": "assistant",
    "message": {"role": "assistant", "content": [
        {"type": "thinking", "thinking": "just planning, no text or tools"}]}}
TOOL_USE_NO_SALIENT_KEY = {"turnId": 8, "type": "assistant",
    "message": {"role": "assistant", "content": [
        {"type": "tool_use", "name": "TodoWrite", "input": {"todos": [{"content": "x"}]}}]}}
RESULT_REC_LIST_CONTENT = {"turnId": 9, "type": "user",
    "message": {"role": "user", "content": [
        {"type": "tool_result",
         "content": [{"type": "text", "text": "structured output line"}],
         "is_error": False}]}}


def _emit_records():
    return [
        {"turnId": 0, "type": "user", "message": {"role": "user", "content": [{"type": "text", "text": "hi"}]}},
        {"turnId": 1, "type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "content": "Z" * 900}]}},
        {"turnId": 2, "type": "file-history-snapshot", "message": {}},
    ]


class TestProjectRecord(unittest.TestCase):
    def test_full_is_identity(self):
        assert tv.project_record(ASSISTANT, "full", 400) == ASSISTANT

    def test_conversation_keeps_text_and_thinking_drops_tools(self):
        out = tv.project_record(ASSISTANT, "conversation", 400)
        kinds = [b["type"] for b in out["message"]["content"]]
        assert kinds == ["thinking", "text"]  # tool_use removed
        assert out["turnId"] == 1

    def test_conversation_drops_tool_result_record(self):
        assert tv.project_record(TOOL_RESULT, "conversation", 400) is None

    def test_conversation_drops_structural_noise(self):
        assert tv.project_record(NOISE, "conversation", 400) is None

    def test_activity_keeps_tool_use_and_truncates_tool_result(self):
        au = tv.project_record(ASSISTANT, "activity", 400)
        assert [b["type"] for b in au["message"]["content"]] == ["thinking", "text", "tool_use"]
        tr = tv.project_record(TOOL_RESULT, "activity", 400)
        block = tr["message"]["content"][0]
        assert block["type"] == "tool_result"
        assert len(block["content"]) < 5000
        assert block.get("_truncated") is True

    def test_activity_drops_structural_noise(self):
        assert tv.project_record(NOISE, "activity", 400) is None

    def test_unknown_view_raises(self):
        with self.assertRaises(ValueError):
            tv.project_record(ASSISTANT, "bogus", 400)

    def test_conversation_strips_non_essential_top_level_fields(self):
        out = tv.project_record(WITH_TRANSPORT_METADATA, "conversation", 400)
        assert "toolUseResult" not in out
        assert "uuid" not in out
        assert "cwd" not in out
        assert out["turnId"] == 4
        assert out["type"] == "assistant"
        assert out["timestamp"] == "2026-08-15T00:00:00Z"
        assert out["message"]["content"][0]["type"] == "text"

    def test_activity_strips_non_essential_top_level_fields(self):
        out = tv.project_record(WITH_TRANSPORT_METADATA, "activity", 400)
        assert "toolUseResult" not in out
        assert "uuid" not in out
        assert "cwd" not in out
        assert out["turnId"] == 4
        assert out["type"] == "assistant"
        assert out["timestamp"] == "2026-08-15T00:00:00Z"

    def test_full_view_keeps_top_level_fields_unchanged(self):
        out = tv.project_record(WITH_TRANSPORT_METADATA, "full", 400)
        assert out == WITH_TRANSPORT_METADATA
        assert out is WITH_TRANSPORT_METADATA

    def test_skeleton_keeps_text_digests_tooluse_drops_thinking(self):
        out = tv.project_record(ASSIST_FULL, "skeleton", 400)
        kinds = [b["type"] for b in out["message"]["content"]]
        assert kinds == ["text", "tool_use"]          # thinking dropped
        tu = out["message"]["content"][1]
        assert tu["name"] == "Bash"
        assert tu["digest"] == "pytest tests/ -q"      # command as digest
        assert "inputBytes" in tu
        assert "toolUseResult" not in out             # top-level stripped
        assert out["turnId"] == 5

    def test_skeleton_summarizes_tool_result_no_body(self):
        out = tv.project_record(RESULT_REC, "skeleton", 400)
        b = out["message"]["content"][0]
        assert b["type"] == "tool_result"
        assert b["last"].strip() == "3 passed in 1.2s"  # last line preserved
        assert b["bytes"] > 5000                          # size recorded
        assert "x"*5000 not in json.dumps(b)              # body NOT included
        assert b["isError"] is False

    def test_skeleton_is_a_known_view(self):
        assert "skeleton" in tv.VIEWS

    def test_skeleton_drops_thinking_only_record(self):
        assert tv.project_record(THINKING_ONLY, "skeleton", 400) is None

    def test_skeleton_tool_use_without_salient_key_still_emits_empty_digest(self):
        out = tv.project_record(TOOL_USE_NO_SALIENT_KEY, "skeleton", 400)
        tu = out["message"]["content"][0]
        assert tu["type"] == "tool_use"
        assert tu["digest"] == ""
        assert "inputBytes" in tu

    def test_skeleton_summarizes_structured_list_tool_result(self):
        out = tv.project_record(RESULT_REC_LIST_CONTENT, "skeleton", 400)
        b = out["message"]["content"][0]
        assert b["type"] == "tool_result"
        assert b["bytes"] > 0
        assert b["isError"] is False


class TestEmitViews(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_emit_writes_header_then_records(self):
        paths = tv.emit_views(_emit_records(), ["conversation"], self.tmp, 400, "abc123")
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

    def test_emit_activity_records_truncation_count(self):
        paths = tv.emit_views(_emit_records(), ["activity"], self.tmp, 400, "abc123")
        header = json.loads(paths["activity"].read_text().splitlines()[0])
        assert header["_truncated"] == {"toolResultTruncLen": 400, "count": 1}

    def test_emit_header_records_kept_top_level_fields_for_non_full_view(self):
        paths = tv.emit_views(_emit_records(), ["conversation"], self.tmp, 400, "abc123")
        header = json.loads(paths["conversation"].read_text().splitlines()[0])
        assert header["_keptTopLevelFields"] == ["turnId", "type", "message", "timestamp"]


if __name__ == "__main__":
    unittest.main()
