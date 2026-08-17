#!/usr/bin/env python3
# scripts/pull_turn.py
"""Deterministically pull one turn's full body from a raw transcript, by turnId.

The single place that knows the transcript's JSON shape for on-demand retrieval — a
skeleton-view lens calls this instead of hand-writing jq/grep. Field selectors return the
full, UNtruncated content the skeleton summarized."""
import argparse
import json
import sys
from pathlib import Path

_FIELD_BLOCK = {"text": "text", "thinking": "thinking",
                "tool_input": "tool_use", "tool_result": "tool_result"}


def _record(transcript_path, turn_id):
    with open(transcript_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            if o.get("_view"):
                continue
            if o.get("turnId") == turn_id:
                return o
    raise KeyError("turnId {} not found in {}".format(turn_id, transcript_path))


def _extract_field(record, field):
    if field is None:
        return json.dumps(record)
    block_type = _FIELD_BLOCK.get(field)
    if block_type is None:
        raise ValueError("unknown field {!r}".format(field))
    msg = record.get("message") or {}
    content = msg.get("content")
    if isinstance(content, str):
        return content if field == "text" else ""
    parts = []
    for b in (content or []):
        if not isinstance(b, dict) or b.get("type") != block_type:
            continue
        if block_type == "text":
            parts.append(b.get("text", ""))
        elif block_type == "thinking":
            parts.append(b.get("thinking", ""))
        elif block_type == "tool_use":
            parts.append(json.dumps(b.get("input", "")))
        elif block_type == "tool_result":
            c = b.get("content")
            parts.append(c if isinstance(c, str) else json.dumps(c))
    # Multiple blocks of the same field in one turn are joined and returned as one string
    # (Claude Code emits at most one tool_result per turn today, so this is latent).
    return "\n".join(parts)


def pull(transcript_path, turn_id, field=None):
    o = _record(transcript_path, turn_id)
    return _extract_field(o, field)


def pull_batch(transcript_path, turn_ids, field=None):
    """Scan the transcript once, returning {turnId: body} for every id present.

    Ids not found in the transcript are simply absent from the returned dict —
    callers must check membership rather than assume every requested id resolved.
    """
    wanted = set(turn_ids)
    found = {}
    with open(transcript_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            if o.get("_view"):
                continue
            tid = o.get("turnId")
            if tid in wanted:
                found[tid] = _extract_field(o, field)
                if len(found) == len(wanted):
                    break
    return found


def main(argv=None):
    ap = argparse.ArgumentParser(description="Pull one turn, or a batch of turns, by turnId")
    ap.add_argument("transcript", type=Path)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("turn_id", type=int, nargs="?", default=None)
    group.add_argument("--ids", help="comma-separated turnIds for batch mode, e.g. 12,47,301")
    ap.add_argument("--field", choices=sorted(_FIELD_BLOCK))
    args = ap.parse_args(argv)

    if args.ids is not None:
        requested = [int(tid) for tid in args.ids.split(",")]
        try:
            found = pull_batch(args.transcript, requested, field=args.field)
        except FileNotFoundError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        missing = [tid for tid in requested if tid not in found]
        if missing:
            print("turnId(s) not found: {}".format(", ".join(str(m) for m in missing)),
                  file=sys.stderr)
        sys.stdout.write(json.dumps({str(tid): body for tid, body in found.items()}))
        return 2 if not found else 0

    try:
        sys.stdout.write(pull(args.transcript, args.turn_id, field=args.field))
        return 0
    except KeyError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
