#!/usr/bin/env python3
"""Emit the requested transcript views for a pack. CLI wrapper over transcript_views.

Usage: build_views.py <transcript.jsonl> <out_dir> <view> [<view> ...]
`full` is materialized too when requested (a header-stamped copy) — the dispatcher may still
point full-view lenses at the original transcript.jsonl instead; both are valid.
"""
import argparse
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import merge_sessions  # noqa: E402
import transcript_views  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description="Emit transcript views")
    ap.add_argument("transcript", type=Path)
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("views", nargs="+")
    ap.add_argument("--tool-result-trunc-len", type=int, default=400)
    args = ap.parse_args(argv)

    bad = [v for v in args.views if v not in transcript_views.VIEWS]
    if bad:
        print(f"Unknown view(s): {bad}; choose from {transcript_views.VIEWS}", file=sys.stderr)
        return 2

    if not args.transcript.is_file():
        print(f"Transcript not found: {args.transcript}", file=sys.stderr)
        return 2

    sha = hashlib.sha256(args.transcript.read_bytes()).hexdigest()
    records = merge_sessions._load(args.transcript)
    paths = transcript_views.emit_views(records, args.views, args.out_dir,
                                         args.tool_result_trunc_len, sha)
    print(f"Emitted views: {{{', '.join(f'{v}: {p}' for v, p in paths.items())}}}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
