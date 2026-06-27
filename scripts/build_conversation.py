#!/usr/bin/env python3
"""Assemble the whole-conversation transcript for an eval pack.

Merges every session archived for this repo (the .eval-packs/sessions store,
where the .jsonl files are the source of truth) with the current live
transcript, deduped by uuid and time-ordered, into one merged JSONL. Anchor:
the eval runs on the entire conversation, not just the latest resumed session.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archive_session  # noqa: E402
import merge_sessions  # noqa: E402


def build(cwd, current_transcript, out_path):
    """Merge archived repo sessions + the current transcript into out_path.

    Returns {"sessions": n, "entries": m, "paths": [...]}. Writes nothing when
    there is no archive and no current transcript.
    """
    repo_root = archive_session.resolve_repo_root(cwd)
    paths = list(archive_session.list_archived_sessions(repo_root)) if repo_root else []
    seen = {p.resolve() for p in paths}
    cur = Path(current_transcript) if current_transcript else None
    if cur and cur.is_file() and cur.resolve() not in seen:
        paths.append(cur)
    if not paths:
        return {"sessions": 0, "entries": 0, "paths": []}
    n = merge_sessions.write_merged(paths, out_path)
    return {"sessions": len(paths), "entries": n, "paths": [str(p) for p in paths]}


def main():
    parser = argparse.ArgumentParser(
        description="Assemble the whole-conversation transcript")
    parser.add_argument("cwd")
    parser.add_argument("current_transcript")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    res = build(args.cwd, args.current_transcript, args.output)
    print(f"Assembled conversation: {res['sessions']} session(s), "
          f"{res['entries']} entries -> {args.output}")


if __name__ == "__main__":
    main()
