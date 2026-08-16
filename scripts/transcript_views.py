"""Deterministic transcript projections. Pure functions: record in -> fragment out, no I/O.

Views (append-only vocabulary):
  full          - identity; the raw record unchanged.
  conversation  - real user + assistant text + thinking. No tool payloads, no structural noise.
  activity      - conversation + tool_use (name/input) + truncated tool_result + exit codes.
"""
import copy
import json
from pathlib import Path

VIEWS = ("full", "conversation", "activity")
VIEW_VERSION = "1.0.0"

# Top-level record types that are pure structure/noise — dropped by every non-full view.
DROPPABLE_TYPES = frozenset({
    "file-history-snapshot", "file-history-delta", "queue-operation",
    "attachment", "ai-title", "last-prompt", "mode", "pr-link", "system",
})

# Content-block types kept by each non-full view.
_CONVERSATION_BLOCKS = frozenset({"text", "thinking"})
_ACTIVITY_BLOCKS = frozenset({"text", "thinking", "tool_use", "tool_result"})

# Top-level record keys kept by non-full views. Everything else — toolUseResult
# (Claude Code's untruncated duplicate of every tool result) and transport metadata
# (uuid, sessionId, cwd, gitBranch, requestId, ...) — is dropped as noise no lens grades.
_KEEP_TOP_ORDER = ("turnId", "type", "message", "timestamp")
_KEEP_TOP = frozenset(_KEEP_TOP_ORDER)


def _json_len_safe(content):
    try:
        return json.dumps(content)
    except (TypeError, ValueError):
        return str(content)


def _truncate_tool_result(block, limit):
    b = copy.deepcopy(block)
    content = b.get("content")
    text = content if isinstance(content, str) else _json_len_safe(content)
    if isinstance(text, str) and len(text) > limit:
        head = limit // 2
        tail = limit - head
        b["content"] = text[:head] + "\n…[truncated]…\n" + text[-tail:]
        b["_truncated"] = True
    return b


def project_record(record, view, tool_result_trunc_len):
    """Project one raw record into `view`. Returns the projected dict, or None if dropped.

    `turnId` is always preserved on a kept record (the citation coordinate)."""
    if view == "full":
        return record
    if view not in VIEWS:
        raise ValueError("unknown view {!r}; expected one of {}".format(view, VIEWS))
    if record.get("type") in DROPPABLE_TYPES:
        return None

    keep_blocks = _CONVERSATION_BLOCKS if view == "conversation" else _ACTIVITY_BLOCKS
    out = copy.deepcopy(record)
    msg = out.get("message")
    content = msg.get("content") if isinstance(msg, dict) else None

    if isinstance(content, list):
        projected = []
        for block in content:
            if not isinstance(block, dict):
                continue
            bt = block.get("type")
            if bt not in keep_blocks:
                continue
            if bt == "tool_result":
                projected.append(_truncate_tool_result(block, tool_result_trunc_len))
            else:
                projected.append(block)
        # A record whose blocks are ALL dropped (e.g. a tool_result record under conversation)
        # carries no signal for this view — drop the record entirely.
        if not projected:
            return None
        msg["content"] = projected
    elif isinstance(content, str):
        pass  # string content is conversational text; keep as-is
    return {k: v for k, v in out.items() if k in _KEEP_TOP}


def _dropped_reason(record, view):
    """Why a record was dropped from a non-full view — a type label for the header counts."""
    t = record.get("type")
    if t in DROPPABLE_TYPES:
        return t
    # dropped because every content block was filtered out — label by the blocks it held
    msg = record.get("message") or {}
    content = msg.get("content")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type"):
                return block["type"]
    return "empty"


def emit_views(records, views, out_dir, tool_result_trunc_len, source_sha256):
    """Project `records` into each requested view and write one JSONL per view. Returns {view: Path}.
    The full view is a straight copy (header still prepended for provenance)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    result = {}
    for view in views:
        dropped, trunc_count, body = {}, 0, []
        for rec in records:
            projected = project_record(rec, view, tool_result_trunc_len)
            if projected is None:
                key = _dropped_reason(rec, view)
                dropped[key] = dropped.get(key, 0) + 1
                continue
            if view == "activity":
                for b in (projected.get("message", {}).get("content") or []):
                    if isinstance(b, dict) and b.get("_truncated"):
                        trunc_count += 1
            body.append(projected)
        header = {
            "_view": view,
            "_viewVersion": VIEW_VERSION,
            "_sourceTranscriptSha256": source_sha256,
            "_dropped": dropped,
            "_truncated": {"toolResultTruncLen": tool_result_trunc_len, "count": trunc_count},
            "_fullPath": str(out_dir.parent / "transcript.jsonl"),
            "_keptTopLevelFields": list(_KEEP_TOP_ORDER) if view != "full" else None,
        }
        path = out_dir / (view + ".jsonl")
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps(header) + "\n")
            for rec in body:
                f.write(json.dumps(rec) + "\n")
        result[view] = path
    return result
