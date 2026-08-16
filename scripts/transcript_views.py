"""Deterministic transcript projections. Pure functions: record in -> fragment out, no I/O.

Views (append-only vocabulary):
  full          - identity; the raw record unchanged.
  conversation  - real user + assistant text + thinking. No tool payloads, no structural noise.
  activity      - conversation + tool_use (name/input) + truncated tool_result + exit codes.
"""
import copy
import json

VIEWS = ("full", "conversation", "activity")

# Top-level record types that are pure structure/noise — dropped by every non-full view.
DROPPABLE_TYPES = frozenset({
    "file-history-snapshot", "file-history-delta", "queue-operation",
    "attachment", "ai-title", "last-prompt", "mode", "pr-link", "system",
})

# Content-block types kept by each non-full view.
_CONVERSATION_BLOCKS = frozenset({"text", "thinking"})
_ACTIVITY_BLOCKS = frozenset({"text", "thinking", "tool_use", "tool_result"})


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
    return out
