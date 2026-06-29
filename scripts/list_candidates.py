#!/usr/bin/env python3
"""Unified, relevance-tagged candidate sessions for the whole-conversation picker.

Combines the archive store (Phase 1) and Claude Code-dir discovery (Phase 3) into
one deduped list, excludes the current session, and flags each candidate as
`relevant` when its branch-set contains the current branch. The skill presents
this list; same-branch (relevant) candidates are pre-checked, but every
inclusion is the user's explicit choice — nothing is auto-merged here.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archive_session  # noqa: E402
import discover_sessions  # noqa: E402


def list_candidates(cwd, current_session_id, current_branch, config_dir=None):
    """Return prior-session candidates (relevant first, then newest)."""
    candidates = {}

    repo_root = archive_session.resolve_repo_root(cwd)
    if repo_root:
        for path in archive_session.list_archived_sessions(repo_root):
            sid = path.stem
            if sid == current_session_id:
                continue
            preview = discover_sessions._session_preview(path)
            candidates[sid] = {
                "sessionId": sid,
                "transcriptPath": str(path),
                "source": "archive",
                **preview,
            }

    for cand in discover_sessions.discover(cwd, config_dir=config_dir):
        sid = cand["sessionId"]
        if sid == current_session_id or sid in candidates:
            continue
        candidates[sid] = {**cand, "source": "discovered"}

    result = []
    for c in candidates.values():
        c["relevant"] = current_branch in (c.get("branches") or [])
        result.append(c)

    result.sort(
        key=lambda c: (c["relevant"], c["timeRange"][0] if c["timeRange"] else ""),
        reverse=True,
    )
    return result


def main():
    parser = argparse.ArgumentParser(
        description="List relevance-tagged prior-session candidates")
    parser.add_argument("cwd")
    parser.add_argument("current_session_id")
    parser.add_argument("current_branch")
    args = parser.parse_args()
    print(json.dumps(
        list_candidates(args.cwd, args.current_session_id, args.current_branch),
        indent=2))


if __name__ == "__main__":
    main()
