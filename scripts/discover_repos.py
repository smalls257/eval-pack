#!/usr/bin/env python3
"""Discover every git repo/worktree an assembled eval-pack transcript touched.

Today's evaluator only diffs the cwd's repo, so work done in a different repo
or worktree during the session — often exactly where a sub-agent did the real
work — is invisible and confidence scores are computed on a partial change
surface (Sensor: the boundary of "what changed" must be observable, not
assumed from process.cwd()). This module restores that visibility: it scans
the transcript for every directory the session referenced (cwd, edited file
paths, `cd` targets), resolves each to its git worktree, and reports each
worktree as a distinct entry since distinct worktrees have distinct branches
and distinct diffs even when they share one underlying repo.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

FILE_TOOLS = {"Edit", "Write", "Read", "MultiEdit", "NotebookEdit"}
GIT_TIMEOUT_SECS = 10

# First `cd <absolute-path>` argument in a shell command. Deliberately
# excludes `cd -`, `cd ~...`, and relative paths — those don't identify a
# repo without shell state we don't have, and a wrong guess here would be a
# Silent Fallback (a fabricated repo location presented as a real signal).
_CD_PATTERN = re.compile(r"(?:^|[;&|]|&&|\|\|)\s*cd\s+(/[^\s;&|]+)")


def _iter_entries(transcript_path):
    """Yield parsed JSON objects, skipping blank/malformed lines silently."""
    with open(transcript_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(entry, dict):
                yield entry


def _cd_targets(command):
    return _CD_PATTERN.findall(command or "")


def _candidate_dirs(entries):
    """Multiset of candidate directories -> list of signal names per hit.

    Returns a list of (dir_str, signal) hits (not yet deduped) so callers can
    both dedupe for the (expensive) git resolution and still count touches
    per repo afterwards by mapping hits back to resolved repos.
    """
    hits = []
    for entry in entries:
        cwd = entry.get("cwd")
        if isinstance(cwd, str) and cwd.startswith("/"):
            hits.append((cwd, "cwd"))

        message = entry.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            name = block.get("name")
            inp = block.get("input") or {}
            if not isinstance(inp, dict):
                continue
            if name in FILE_TOOLS:
                file_path = inp.get("file_path")
                if isinstance(file_path, str) and file_path.startswith("/"):
                    hits.append((str(Path(file_path).parent), "file_path"))
            elif name == "Bash":
                for target in _cd_targets(inp.get("command")):
                    hits.append((target, "cd"))
    return hits


def _git(args, cwd):
    try:
        out = subprocess.run(
            ["git", "-C", str(cwd)] + args,
            capture_output=True, text=True, timeout=GIT_TIMEOUT_SECS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip()


def _resolve_repo(dir_path):
    """Resolve a directory to its repo identity, or None if not a git repo.

    Returns {"repoRoot", "gitCommonDir", "branch", "head"}. A single failed
    git call means "not a resolvable repo here" — skip it, don't crash the
    scan (one bad candidate must not black-box the whole discovery run).
    """
    root = _git(["rev-parse", "--show-toplevel"], dir_path)
    if not root:
        return None
    common_dir = _git(["rev-parse", "--git-common-dir"], dir_path) or ""
    if common_dir and not common_dir.startswith("/"):
        common_dir = str((Path(dir_path) / common_dir).resolve())
    branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], dir_path) or ""
    head = _git(["rev-parse", "HEAD"], dir_path) or ""
    return {
        "repoRoot": root,
        "gitCommonDir": common_dir,
        "branch": branch,
        "head": head,
    }


def discover(transcript_path):
    """Distinct repos/worktrees touched by the session, most-touched first."""
    entries = list(_iter_entries(transcript_path))
    hits = _candidate_dirs(entries)

    unique_dirs = sorted({d for d, _ in hits})
    resolved_by_dir = {}
    for d in unique_dirs:
        if not Path(d).is_dir():
            continue
        resolved = _resolve_repo(d)
        if resolved:
            resolved_by_dir[d] = resolved

    by_root = {}
    for raw_dir, signal in hits:
        resolved = resolved_by_dir.get(raw_dir)
        if not resolved:
            continue
        root = resolved["repoRoot"]
        bucket = by_root.setdefault(root, {
            "repoRoot": root,
            "gitCommonDir": resolved["gitCommonDir"],
            "branch": resolved["branch"],
            "head": resolved["head"],
            "touchCount": 0,
            "signals": set(),
        })
        bucket["touchCount"] += 1
        bucket["signals"].add(signal)

    results = [
        {**bucket, "signals": sorted(bucket["signals"])}
        for bucket in by_root.values()
    ]
    results.sort(key=lambda r: (-r["touchCount"], r["repoRoot"]))
    return results


def main():
    if len(sys.argv) != 2:
        print("usage: discover_repos.py <transcript.jsonl>", file=sys.stderr)
        sys.exit(2)
    print(json.dumps(discover(sys.argv[1]), indent=2))


if __name__ == "__main__":
    main()
