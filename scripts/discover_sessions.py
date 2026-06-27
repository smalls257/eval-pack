#!/usr/bin/env python3
"""Discover Claude Code sessions for this repo that are not yet archived.

Layer 2 (fallback/backfill) of whole-conversation eval: reads Claude Code's own
transcript directories across the repo's git worktrees and returns candidate
sessions still within Claude Code's retention but absent from our archive.
Isolated behind this one module (Buffer) so a Claude Code format change touches
only here. The interface returns preview metadata for a human to choose from.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archive_session  # noqa: E402


def _default_config_dir():
    base = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(base) if base else Path.home() / ".claude"


def _encode_project_slug(path):
    """Encode an absolute cwd the way Claude Code names its project dir."""
    return str(path).replace("/", "-")


def _worktree_dirs(cwd):
    """Absolute paths of every git worktree for the repo containing cwd."""
    try:
        out = subprocess.run(
            ["git", "-C", str(cwd), "worktree", "list", "--porcelain"],
            capture_output=True, text=True,
        )
    except OSError:
        return []
    if out.returncode != 0:
        return []
    dirs = []
    for line in out.stdout.splitlines():
        if line.startswith("worktree "):
            dirs.append(line[len("worktree "):].strip())
    return dirs


def _session_preview(path):
    """Extract {firstPrompt, branches, timeRange, msgCount} from a transcript."""
    first_prompt = ""
    branches = set()
    timestamps = []
    msg_count = 0
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if e.get("gitBranch"):
                    branches.add(e["gitBranch"])
                if e.get("timestamp"):
                    timestamps.append(e["timestamp"])
                if e.get("type") in ("user", "assistant") and e.get("message"):
                    msg_count += 1
                    if not first_prompt and e.get("type") == "user":
                        first_prompt = _first_text(e["message"].get("content"))
    except OSError:
        # Bounded on purpose: an unreadable transcript still surfaces as a
        # candidate (empty preview), rather than vanishing from discovery.
        pass
    timestamps.sort()
    return {
        "firstPrompt": first_prompt,
        "branches": sorted(branches),
        "timeRange": [timestamps[0], timestamps[-1]] if timestamps else [],
        "msgCount": msg_count,
    }


def _first_text(content):
    if isinstance(content, list):
        content = next(
            (p.get("text") for p in content
             if isinstance(p, dict) and p.get("type") == "text"),
            None,
        )
    if isinstance(content, str) and content.strip() and not content.startswith("<"):
        return content.strip().replace("\n", " ")[:80]
    return ""


def discover(cwd, config_dir=None):
    """Return repo session candidates not already archived (newest first).

    Each candidate: {sessionId, transcriptPath, firstPrompt, branches,
    timeRange, msgCount}.
    """
    config_dir = Path(config_dir) if config_dir else _default_config_dir()
    repo_root = archive_session.resolve_repo_root(cwd)
    archived = set()
    if repo_root:
        archived = {p.stem for p in archive_session.list_archived_sessions(repo_root)}

    candidates = []
    seen = set()
    worktrees = _worktree_dirs(cwd) or [str(cwd)]
    # Always include the raw cwd so that symlink-aliased paths (e.g. /var vs
    # /private/var on macOS) are checked even when git normalises them away.
    if str(cwd) not in worktrees:
        worktrees = [str(cwd)] + worktrees
    for worktree in worktrees:
        # Claude Code names project dirs from the raw process.cwd() which may
        # differ from the canonical path that git returns (e.g. /var vs
        # /private/var on macOS).  Try both the raw path and the resolved path
        # so that transcripts are found regardless of which alias was active.
        worktree_path = Path(worktree)
        candidate_slugs = {_encode_project_slug(worktree)}
        try:
            candidate_slugs.add(_encode_project_slug(worktree_path.resolve()))
        except OSError:
            pass
        proj_dirs = [
            config_dir / "projects" / slug
            for slug in candidate_slugs
            if (config_dir / "projects" / slug).is_dir()
        ]
        for proj in proj_dirs:
            for jsonl in sorted(proj.glob("*.jsonl")):
                sid = jsonl.stem
                if sid in archived or sid in seen:
                    continue
                seen.add(sid)
                candidates.append({
                    "sessionId": sid,
                    "transcriptPath": str(jsonl),
                    **_session_preview(jsonl),
                })
    candidates.sort(key=lambda c: (c["timeRange"][0] if c["timeRange"] else ""),
                    reverse=True)
    return candidates


def main():
    parser = argparse.ArgumentParser(
        description="Discover repo sessions not yet archived")
    parser.add_argument("cwd")
    args = parser.parse_args()
    print(json.dumps(discover(args.cwd), indent=2))


if __name__ == "__main__":
    main()
