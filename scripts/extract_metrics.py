#!/usr/bin/env python3
import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


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


def extract_subagent_tokens(entries):
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
                model = tool_model.get(tid, "unknown")
                inner = block.get("content", "")
                if isinstance(inner, list):
                    inner = " ".join(b.get("text", "") for b in inner if isinstance(b, dict))
                m = re.search(r"total_tokens: (\d+)", str(inner))
                if m:
                    model_tokens[model] += int(m.group(1))

    total = sum(model_tokens.values())
    by_model = [{"model": k, "totalTokens": v} for k, v in sorted(model_tokens.items())]
    return total, by_model


def run_git(args):
    try:
        result = subprocess.run(["git"] + args, capture_output=True, text=True)
        return result.stdout if result.returncode == 0 else ""
    except Exception:
        return ""


def get_diff_stats():
    diff_base = ""
    if run_git(["rev-parse", "HEAD~1"]).strip():
        diff_base = "HEAD~1"
    elif run_git(["rev-parse", "HEAD"]).strip():
        empty_tree = run_git(["hash-object", "-t", "tree", "/dev/null"]).strip()
        if empty_tree:
            diff_base = empty_tree

    if not diff_base:
        return 0, 0, 0, []

    diff_stat = run_git(["diff", "--stat", diff_base])
    changed_names_raw = run_git(["diff", "--name-only", diff_base])

    files_changed = diff_stat.count(" | ")

    insertions = 0
    deletions = 0
    if diff_stat:
        last_line = diff_stat.strip().split("\n")[-1]
        m = re.search(r"(\d+) insertion", last_line)
        if m:
            insertions = int(m.group(1))
        m = re.search(r"(\d+) deletion", last_line)
        if m:
            deletions = int(m.group(1))

    changed_files = [f for f in changed_names_raw.splitlines() if f.strip()]
    return files_changed, insertions, deletions, changed_files


def main():
    if len(sys.argv) < 3:
        print("Usage: extract_metrics.py <transcript.jsonl> <output-dir>", file=sys.stderr)
        sys.exit(1)

    transcript_file = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])

    if not transcript_file.is_file():
        print(f"Error: transcript file not found: {transcript_file}", file=sys.stderr)
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)
    entries = load_jsonl(transcript_file)

    turn_types = {"user", "human", "assistant"}
    turn_count = sum(1 for e in entries if e.get("type") in turn_types)
    assistant_entries = [e for e in entries if e.get("type") == "assistant"]

    model = "unknown"
    for e in reversed(assistant_entries):
        m = get_model(e)
        if m:
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

    model_map = defaultdict(lambda: {"inputTokens": 0, "outputTokens": 0})
    for e in assistant_entries:
        m = get_model(e) or "unknown"
        u = get_usage(e)
        model_map[m]["inputTokens"] += u.get("input_tokens") or 0
        model_map[m]["outputTokens"] += u.get("output_tokens") or 0
    token_by_model = [{"model": k, **v} for k, v in sorted(model_map.items())]

    subagent_total_tokens, subagent_tokens_by_model = extract_subagent_tokens(entries)
    files_changed, insertions, deletions, changed_files = get_diff_stats()

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
