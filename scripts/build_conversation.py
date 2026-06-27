#!/usr/bin/env python3
"""Assemble the whole-conversation transcript for an eval pack.

Merges the current session with an explicit, user-confirmed list of prior
sessions (the Phase-4 picker) — nothing is auto-included except the current
transcript. Each included session also contributes its sub-agent transcripts.
Output is deduped by uuid and time-ordered. Anchor: the eval runs on the
conversation the user confirms as relevant, not on whatever happens to be in
the repo's session store.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import merge_sessions  # noqa: E402


def subagent_files(transcript_path):
    """Sub-agent transcripts for a session: <dir>/<stem>/subagents/*.jsonl."""
    p = Path(transcript_path)
    sub = p.parent / p.stem / "subagents"
    return sorted(sub.glob("*.jsonl")) if sub.is_dir() else []


def build(current_transcript, current_session_id, out_path,
          selected_paths=None, include_subagents=True):
    """Merge the current session + explicitly selected sessions into out_path.

    Nothing is auto-included except the current transcript; `selected_paths`
    are the user-confirmed prior sessions (Phase 4 picker). Each included
    session also contributes its sub-agent transcripts. Returns
    {"sessions": n, "entries": m, "subagentFiles": k, "paths": [...]}.
    Writes nothing when there is no current transcript and no selection.
    """
    # current_session_id is accepted for CLI symmetry with list_candidates and
    # to make the call site self-documenting; merge identity is handled by
    # resolved-path dedup below, so it is intentionally not read here.
    _ = current_session_id
    chosen = []
    seen = set()
    for raw in [current_transcript] + list(selected_paths or []):
        if not raw:
            continue
        p = Path(raw)
        if not p.is_file():
            continue
        r = p.resolve()
        if r in seen:
            continue
        seen.add(r)
        chosen.append(p)

    all_paths = []
    subagent_count = 0
    for p in chosen:
        all_paths.append(p)
        if include_subagents:
            subs = subagent_files(p)
            subagent_count += len(subs)
            all_paths.extend(subs)

    if not all_paths:
        return {"sessions": 0, "entries": 0, "subagentFiles": 0, "paths": []}
    n = merge_sessions.write_merged(all_paths, out_path)
    return {
        "sessions": len(chosen),
        "entries": n,
        "subagentFiles": subagent_count,
        "paths": [str(p) for p in chosen],
    }


def main():
    parser = argparse.ArgumentParser(
        description="Assemble the whole-conversation transcript")
    parser.add_argument("current_transcript")
    parser.add_argument("current_session_id")
    parser.add_argument("output", type=Path)
    parser.add_argument("--select", action="append", default=[],
                        help="A user-confirmed prior session transcript path "
                             "(repeatable)")
    parser.add_argument("--no-subagents", action="store_true",
                        help="Do not fold in sub-agent transcripts")
    args = parser.parse_args()
    res = build(args.current_transcript, args.current_session_id, args.output,
                selected_paths=args.select,
                include_subagents=not args.no_subagents)
    print(f"Assembled conversation: {res['sessions']} session(s), "
          f"{res['subagentFiles']} sub-agent file(s), {res['entries']} entries "
          f"-> {args.output}")


if __name__ == "__main__":
    main()
