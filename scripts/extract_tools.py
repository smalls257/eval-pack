#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))  # noqa: E402
from config import read_config  # noqa: E402


def load_jsonl(path):
    entries = []
    skipped = 0
    with open(path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                skipped += 1
                print(f"Warning: skipping malformed JSON on line {line_no}", file=sys.stderr)
    if skipped:
        print(f"Warning: {skipped} line(s) skipped due to JSON parse errors", file=sys.stderr)
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
    parser = argparse.ArgumentParser(description="Extract tool uses from transcript")
    parser.add_argument("transcript", help="Path to transcript.jsonl")
    parser.add_argument("output_dir", help="Directory to write tool output")
    parser.add_argument("--config", default=None, help="Path to resolved eval-config.json")
    args = parser.parse_args()
    cfg = read_config(args.config)

    transcript_file = Path(args.transcript)
    output_dir = Path(args.output_dir)

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
        skills.append({"name": name, "args": args[:cfg["skillArgsMaxLen"]]})

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
