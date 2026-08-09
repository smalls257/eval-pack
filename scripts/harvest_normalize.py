"""Pure transforms: source trajectories/dialogues -> eval-pack transcript lines. Stdlib only."""

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
