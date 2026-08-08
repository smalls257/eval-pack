#!/usr/bin/env python3
import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

# Agent results report usage as `subagent_tokens: N`; older/other formats may
# use `total_tokens: N`. Accept either.
DEFAULT_TOKEN_FIELD_RE = re.compile(r"(?:subagent_tokens|total_tokens):\s*(\d+)")


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


def get_usage(entry):
    return (entry.get("message") or entry).get("usage") or {}


def get_model(entry):
    msg = entry.get("message") or entry
    return msg.get("model") or entry.get("model")


def extract_subagent_tokens(entries, token_field_re=DEFAULT_TOKEN_FIELD_RE):
    tool_model = {}
    for entry in entries:
        content = (entry.get("message") or {}).get("content") or entry.get("content") or []
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use" and block.get("name") == "Agent":
                tid = block.get("id")
                inp = block.get("input") or {}
                model = inp.get("model") or inp.get("subagent_type") or "unknown"
                if tid:
                    tool_model[tid] = model

    model_tokens = defaultdict(int)
    for entry in entries:
        content = (entry.get("message") or {}).get("content") or entry.get("content") or []
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_result":
                tid = block.get("tool_use_id", "")
                if tid not in tool_model:  # not an Agent call — skip silently
                    continue
                model = tool_model[tid]
                inner = block.get("content", "")
                if isinstance(inner, list):
                    inner = " ".join(b.get("text", "") for b in inner if isinstance(b, dict))
                m = token_field_re.search(str(inner))
                if m:
                    model_tokens[model] += int(m.group(1))
                else:
                    print(
                        f"Warning: could not parse subagent token usage from Agent tool_result "
                        f"(tool_use_id={tid!r}); subagent token usage for this call will be 0",
                        file=sys.stderr,
                    )

    total = sum(model_tokens.values())
    by_model = [{"model": k, "totalTokens": v} for k, v in sorted(model_tokens.items())]
    return total, by_model


def main():
    parser = argparse.ArgumentParser(description="Extract session metrics from transcript")
    parser.add_argument("transcript_file", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--insertions", type=int, default=0, help="Lines inserted (from git diff --stat)")
    parser.add_argument("--deletions", type=int, default=0, help="Lines deleted (from git diff --stat)")
    parser.add_argument("--files-changed", type=int, default=0, dest="files_changed", help="Number of files changed (from git diff --name-only | wc -l)")
    parser.add_argument(
        "--changed-files", default="[]", dest="changed_files_json",
        help="JSON array of changed file paths",
    )
    parser.add_argument(
        "--config", default=None,
        help="Path to resolved eval-config.json (accepted for CLI/pipeline "
             "compatibility; extraction no longer reads config-driven options)",
    )
    args = parser.parse_args()

    transcript_file = args.transcript_file
    output_dir = args.output_dir

    if not transcript_file.is_file():
        print(f"Error: transcript file not found: {transcript_file}", file=sys.stderr)
        sys.exit(1)

    try:
        changed_files = json.loads(args.changed_files_json)
    except json.JSONDecodeError:
        print("Warning: --changed-files is not valid JSON; using []", file=sys.stderr)
        changed_files = []

    output_dir.mkdir(parents=True, exist_ok=True)
    entries = load_jsonl(transcript_file)

    turn_types = {"user", "human", "assistant"}
    turn_count = sum(1 for e in entries if e.get("type") in turn_types)
    assistant_entries = [e for e in entries if e.get("type") == "assistant"]

    # "<synthetic>" tags Claude Code placeholder turns (e.g. "No response
    # requested." after a local command) — no real inference, zero usage.
    # Exclude it from model attribution so it doesn't show as a $0 model row.
    model = "unknown"
    for e in reversed(assistant_entries):
        m = get_model(e)
        if m and m != "<synthetic>":
            model = m
            break

    input_tokens = sum((get_usage(e).get("input_tokens") or 0) for e in assistant_entries)
    output_tokens = sum((get_usage(e).get("output_tokens") or 0) for e in assistant_entries)
    cache_read_tokens = sum((get_usage(e).get("cache_read_input_tokens") or 0) for e in assistant_entries)
    cache_write_tokens = sum((get_usage(e).get("cache_creation_input_tokens") or 0) for e in assistant_entries)
    total_tokens = input_tokens + output_tokens + cache_read_tokens + cache_write_tokens

    timestamps = [e.get("timestamp") for e in entries if e.get("timestamp")]
    first_ts = timestamps[0] if timestamps else None
    last_ts = timestamps[-1] if timestamps else None

    model_map = defaultdict(lambda: {
        "inputTokens": 0, "outputTokens": 0,
        "cacheReadTokens": 0, "cacheWriteTokens": 0,
    })
    for e in assistant_entries:
        m = get_model(e) or "unknown"
        if m == "<synthetic>":
            continue
        u = get_usage(e)
        model_map[m]["inputTokens"] += u.get("input_tokens") or 0
        model_map[m]["outputTokens"] += u.get("output_tokens") or 0
        model_map[m]["cacheReadTokens"] += u.get("cache_read_input_tokens") or 0
        model_map[m]["cacheWriteTokens"] += u.get("cache_creation_input_tokens") or 0
    token_by_model = [{"model": k, **v} for k, v in sorted(model_map.items())]

    subagent_total_tokens, subagent_tokens_by_model = extract_subagent_tokens(entries)

    files_changed = args.files_changed
    insertions = args.insertions
    deletions = args.deletions
    # changed_files already set above from --changed-files arg

    result = {
        "lastModel": model,
        "inputTokens": input_tokens,
        "outputTokens": output_tokens,
        "totalTokens": total_tokens,
        "turnCount": turn_count,
        "firstTimestamp": first_ts,
        "lastTimestamp": last_ts,
        "filesChanged": files_changed,
        "insertions": insertions,
        "deletions": deletions,
        "changedFilesList": changed_files,
        "cacheReadTokens": cache_read_tokens,
        "cacheWriteTokens": cache_write_tokens,
        "subagentTotalTokens": subagent_total_tokens,
        "tokensByModel": token_by_model,
        "subagentTokensByModel": subagent_tokens_by_model,
    }

    out_path = output_dir / "metrics.json"
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Metrics written to {out_path}")


if __name__ == "__main__":
    main()
