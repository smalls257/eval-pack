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
import os
import subprocess
import sys
from pathlib import Path

WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
READ_TOOLS = {"Read"}
FILE_TOOLS = WRITE_TOOLS | READ_TOOLS
GIT_TIMEOUT_SECS = 10

# Prepended to EVERY git invocation. See _git for the WHY. core.fsmonitor=
# disarms the fsmonitor hook, core.pager=cat disarms the pager, and
# --no-optional-locks stops index refreshes from firing config-driven code.
_GIT_HARDENING_FLAGS = [
    "-c", "core.fsmonitor=",
    "-c", "core.pager=cat",
    "--no-optional-locks",
]

# First `cd <absolute-path>` argument in a shell command. Deliberately
# excludes `cd -`, `cd ~...`, and relative paths — those don't identify a
# repo without shell state we don't have, and a wrong guess here would be a
# Silent Fallback (a fabricated repo location presented as a real signal).
# Matches POSIX absolute paths (`/foo`) and Windows drive-absolute paths
# (`C:\foo`, `C:/foo`) since a Windows session's transcript carries the
# latter — a POSIX-only pattern would silently under-report every `cd` on
# that platform. Known limitation: quoted/spaced paths (`cd "/a b"`) are not
# captured — this errs toward under-reporting, never fabrication; and `cd`
# inside a quoted string can yield a bogus token, but the is_dir() guard in
# discover() drops it before any git call, so a fabricated path never
# reaches subprocess.
_CD_PATTERN = re.compile(r"(?:^|[;&|]|&&|\|\|)\s*cd\s+((?:/|[A-Za-z]:[\\/])[^\s;&|]+)")


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


def _tool_uses(entry):
    """Yield (tool_name, input_dict) for every tool_use block in one entry.

    The SINGLE parser for a transcript entry's tool calls, so discover() and
    discover_write_repos() iterate tool_use blocks identically (Shield: one
    parser, not two divergent ones). Malformed blocks / non-dict inputs are
    skipped silently — the transcript is untrusted input.
    """
    message = entry.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        return
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        inp = block.get("input") or {}
        if not isinstance(inp, dict):
            continue
        yield block.get("name"), inp


def _candidate_dirs(entries):
    """Multiset of candidate directories -> list of signal names per hit.

    Returns a list of (dir_str, signal) hits (not yet deduped) so callers can
    both dedupe for the (expensive) git resolution and still count touches
    per repo afterwards by mapping hits back to resolved repos.
    """
    hits = []
    for entry in entries:
        cwd = entry.get("cwd")
        if isinstance(cwd, str) and os.path.isabs(cwd):
            hits.append((cwd, "cwd"))

        for name, inp in _tool_uses(entry):
            if name in FILE_TOOLS:
                file_path = inp.get("file_path")
                if isinstance(file_path, str) and os.path.isabs(file_path):
                    signal = "write" if name in WRITE_TOOLS else "read"
                    hits.append((str(Path(file_path).parent), signal))
            elif name == "Bash":
                for target in _cd_targets(inp.get("command")):
                    hits.append((target, "cd"))
    return hits


def _git_argv(args, cwd):
    """Construct the hardened argv for a git call — the single source of truth
    so tests and the sibling repo_diffs.py can assert the boundary is present."""
    return ["git"] + _GIT_HARDENING_FLAGS + ["-C", str(cwd)] + list(args)


def _hardened_env():
    """Env that neutralizes attacker-controlled global/system git config while
    keeping the repo-local config these read-only queries legitimately need."""
    env = os.environ.copy()
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env["GIT_CONFIG_GLOBAL"] = "/dev/null"
    env["GIT_CONFIG_SYSTEM"] = "/dev/null"
    return env


def _git(args, cwd):
    """The SINGLE chokepoint every git call in this module goes through.

    Hardened because the dirs come from a (path-uncontrolled) transcript; git
    reads each dir's .git/config, and index-refreshing/paging subcommands
    (diff/status/log — used by the sibling repo-diff step) execute
    config-driven code (core.fsmonitor/pager/etc). The prepended flags plus
    the hardened env neutralize that vector regardless of subcommand, so the
    coming repo_diffs.py inherits a safe boundary by routing through here.
    rev-parse (used today) doesn't trip it, but diff/status/log do — harden
    now so the diff step can't reopen the hole.
    """
    try:
        out = subprocess.run(
            _git_argv(args, cwd),
            capture_output=True, text=True, timeout=GIT_TIMEOUT_SECS,
            env=_hardened_env(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip()


def _expand_long_path(path):
    """Expand a Windows 8.3 SHORT path component (RUNNER~1) to its LONG form.

    No-op on POSIX (there is no short-name concept), and a no-op on Windows for
    any path that doesn't exist on disk — `GetLongPathNameW` can only expand a
    real filesystem entry. This is NOT a Silent Fallback: returning the input
    unchanged when expansion is impossible is the ONLY correct behavior (there
    is no long form to discover for a path that isn't there), and every caller
    routes BOTH sides of a comparison through this same function, so an
    unexpandable path degrades identically on both sides and still matches.

    Why it's needed: on Windows, `os.path.realpath` of a temp dir can return the
    8.3 short form (`C:\\Users\\RUNNER~1\\...`) while git's `--show-toplevel`
    returns the long form (`C:\\Users\\runneradmin\\...`). Without expanding to a
    single canonical (long) form, canon_root would yield different strings for
    the same directory depending on whether its input came from realpath or git.
    """
    if os.name != "nt":
        return path
    import ctypes
    from ctypes import wintypes

    get_long = ctypes.windll.kernel32.GetLongPathNameW
    get_long.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
    get_long.restype = wintypes.DWORD

    buf = ctypes.create_unicode_buffer(len(path) + 260)
    needed = get_long(path, buf, len(buf))
    if needed == 0:
        return path              # path doesn't exist / API failed: leave as-is
    if needed > len(buf):
        buf = ctypes.create_unicode_buffer(needed)
        if get_long(path, buf, len(buf)) == 0:
            return path
    return buf.value


def canon_root(p):
    """Canonicalize a repo root so it compares equal across producers/platforms.

    THE single canonicalization chokepoint for repo-root identity — repo_diffs.py
    and validate_contracts.py both import this instead of reimplementing it, so
    "same repo" always means the same thing (Shield: one normalization, not
    divergent copies that silently drift).

    Two sources produce repoRoot strings that must compare equal even though
    they take different lexical forms:
      - git's `--show-toplevel` (used here and in repo_diffs.py), which on
        Windows prints forward slashes (`C:/Users/...`) and the LONG name.
      - Python's realpath/str(Path) (used by callers building a root from a
        user selection or a tempdir), which on Windows prints backslashes
        (`C:\\Users\\...`) and can print the 8.3 SHORT name (`RUNNER~1`).
    The pipeline resolves all three mismatches into one identity:
      1. `realpath` fixes the separator mismatch (it normalizes slashes
         lexically even for a nonexistent path — no filesystem access needed).
      2. `_expand_long_path` folds an 8.3 short component to its long form so
         a realpath-sourced and a git-sourced path for the same real dir agree.
      3. `normcase` folds case for Windows' case-insensitive filesystem (and
         re-normalizes separators, harmlessly redundant).
    normcase and _expand_long_path are both documented no-ops on POSIX, so this
    function changes nothing about macOS/Linux behavior.
    """
    if not p:
        return p
    return os.path.normcase(_expand_long_path(os.path.realpath(p))).rstrip("/\\")


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
    if common_dir and not os.path.isabs(common_dir):
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


def discover_write_repos(transcript_path):
    """Repos the session WROTE to (Edit/Write/MultiEdit/NotebookEdit file_paths only).

    Resolves git for ONLY the write-signal dirs — far cheaper than full discover()
    on the render hot path, where the coverage gate needs nothing else. Same
    {repoRoot, gitCommonDir, branch, head, signals:['write'], touchCount} shape as
    discover() produces for the write-touched subset, so the coverage gate that reads
    repoRoot/branch/signals keeps working (Engine: full discover() shells ~4 git calls
    per DISTINCT dir referenced anywhere in the transcript — read, cwd, cd included —
    which on a big session is thousands of subprocesses the gate never consults).
    """
    entries = _iter_entries(transcript_path)   # the module's transcript loader
    write_dirs = {}                            # dir -> touchCount, WRITE_TOOLS file_paths only
    for entry in entries:
        for name, inp in _tool_uses(entry):    # the shared tool_use iterator
            if name in WRITE_TOOLS:
                file_path = inp.get("file_path")
                if isinstance(file_path, str) and os.path.isabs(file_path):
                    d = str(Path(file_path).parent)
                    write_dirs[d] = write_dirs.get(d, 0) + 1

    repos = {}
    for d, n in write_dirs.items():
        if not Path(d).is_dir():
            continue
        info = _resolve_repo(d)                 # the existing hardened resolver
        if not info:
            continue
        root = info["repoRoot"]
        if root not in repos:
            repos[root] = {**info, "signals": ["write"], "touchCount": 0}
        repos[root]["touchCount"] += n
    return sorted(repos.values(), key=lambda r: (-r["touchCount"], r["repoRoot"]))


def main():
    if len(sys.argv) != 2:
        print("usage: discover_repos.py <transcript.jsonl>", file=sys.stderr)
        sys.exit(2)
    print(json.dumps(discover(sys.argv[1]), indent=2))


if __name__ == "__main__":
    main()
