#!/usr/bin/env python3
"""Merge multiple Claude Code session transcripts into one ordered JSONL.

Dedup by message uuid (first occurrence wins); entries without a uuid are kept
as-is. Ordered by timestamp (lexical == chronological for ISO-8601 Z stamps;
entries without a timestamp sort first, keeping input order). Anchor:
reconstruct the whole conversation from its scattered session files without
inventing or dropping turns.
"""
import argparse
import json
import sys
from pathlib import Path


def _load(path):
    out = []
    skipped = 0
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    skipped += 1
    except OSError as exc:
        print(f"Warning: could not read {path}: {exc}", file=sys.stderr)
        return out
    if skipped:
        print(f"Warning: {skipped} malformed line(s) skipped in {path}", file=sys.stderr)
    return out


def merge(paths):
    """Return merged, deduped, time-ordered entries from the given paths."""
    seen = set()
    entries = []
    for path in paths:
        for entry in _load(path):
            uid = entry.get("uuid")
            if uid is not None:
                if uid in seen:
                    continue
                seen.add(uid)
            entries.append(entry)
    entries.sort(key=lambda e: e.get("timestamp") or "")
    return entries


def write_merged(paths, out_path):
    """Merge `paths` and write the result to `out_path`; return entry count."""
    entries = merge(paths)
    with open(out_path, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")
    return len(entries)


def main():
    parser = argparse.ArgumentParser(
        description="Merge session transcripts into one ordered JSONL")
    parser.add_argument("output", type=Path)
    parser.add_argument("inputs", nargs="+", type=Path)
    args = parser.parse_args()
    n = write_merged(args.inputs, args.output)
    print(f"Merged {len(args.inputs)} transcript(s) -> {args.output} ({n} entries)")


if __name__ == "__main__":
    main()
