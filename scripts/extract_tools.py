#!/usr/bin/env python3
import json
import sys
from pathlib import Path


def load_jsonl(path):
    entries = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return entries


def extract_tool_uses(entries):
    tool_uses = []
    for entry in entries:
        content = (entry.get("message") or {}).get("content") or entry.get("content") or []
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                tool_uses.append(block)
    return tool_uses


def main():
    if len(sys.argv) < 3:
        print("Usage: extract_tools.py <transcript.jsonl> <output-dir>", file=sys.stderr)
        sys.exit(1)

    transcript_file = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])

    if not transcript_file.is_file():
        print(f"Error: transcript file not found: {transcript_file}", file=sys.stderr)
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)
    entries = load_jsonl(transcript_file)
    tool_uses = extract_tool_uses(entries)

    counts = {}
    for t in tool_uses:
        name = t.get("name", "")
        counts[name] = counts.get(name, 0) + 1
    tool_calls = sorted(
        [{"name": k, "count": v} for k, v in counts.items()],
        key=lambda x: -x["count"],
    )

    subagents = [
        {
            "description": (t.get("input") or {}).get("description", ""),
            "model": (t.get("input") or {}).get("model", "default"),
            "subagentType": (t.get("input") or {}).get("subagent_type", "general-purpose"),
        }
        for t in tool_uses
        if t.get("name") == "Agent"
    ]

    seen_skills = set()
    skills = []
    for t in tool_uses:
        if t.get("name") != "Skill":
            continue
        inp = t.get("input") or {}
        name = inp.get("skill", "")
        if name in seen_skills:
            continue
        seen_skills.add(name)
        args = inp.get("args", "") or ""
        if not isinstance(args, str):
            args = json.dumps(args)
        skills.append({"name": name, "args": args[:200]})

    result = {
        "toolCalls": tool_calls,
        "totalToolCalls": len(tool_uses),
        "subagents": subagents,
        "skills": skills,
    }

    out_path = output_dir / "tools.json"
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Tools written to {out_path}")


if __name__ == "__main__":
    main()
