"""Pure transforms: source trajectories/dialogues -> eval-pack transcript lines. Stdlib only."""

import re as _re

_ROLE = {"system": "system", "user": "user", "ai": "assistant", "assistant": "assistant"}


def _line(role, content):
    return {"type": role, "message": {"role": role, "content": content}}


def swe_trajectory_to_transcript(trajectory, problem_statement):
    lines = [_line("user", problem_statement)]
    for m in trajectory:
        role = _ROLE.get(m.get("role"), m.get("role"))
        text = m.get("text") or m.get("system_prompt") or ""
        if role == "system" or not str(text).strip():
            continue
        lines.append(_line(role, text))
    return lines


def sycon_dialogue_to_transcript(input_messages, final_response):
    lines = []
    for m in input_messages:
        role = _ROLE.get(m.get("role"), m.get("role"))
        content = m.get("content") or ""
        if role == "system" or not str(content).strip():
            continue
        lines.append(_line(role, content))
    if str(final_response).strip():
        lines.append(_line("assistant", final_response))
    return lines


_NOISE = _re.compile(r"^\s*(<ide_opened_file>.*?</ide_opened_file>|<system-reminder>.*?</system-reminder>)\s*$", _re.DOTALL)


def _content_text(content):
    if isinstance(content, str):
        return content
    parts = []
    for b in content or []:
        if not isinstance(b, dict):
            continue
        if b.get("type") == "text":
            parts.append(b.get("text", ""))
        elif b.get("type") == "tool_use":
            parts.append("[tool: {}]".format(b.get("name", "?")))
    return "\n".join(p for p in parts if p)


def claude_session_to_transcript(lines):
    out = []
    for d in lines:
        if d.get("type") not in ("user", "assistant"):
            continue
        m = d.get("message") or {}
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        text = _content_text(m.get("content"))
        if not text.strip() or _NOISE.match(text.strip()):
            continue
        out.append(_line(role, text))
    return out
