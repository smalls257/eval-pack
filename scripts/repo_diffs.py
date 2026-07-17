#!/usr/bin/env python3
"""Compute the diff for every repo the user confirmed evaluating, against their chosen base.

discover_repos.py finds every repo/worktree a session touched, but touching isn't the same
as "in scope for this eval" — the user picks which repos and which base ref (Anchor: the
confidence/risk analysis must reason about the change surface the human actually intended,
not one inferred from process.cwd()). This script takes that confirmed {repo, base} selection
and turns it into the one artifact — repo-diffs.json — the evaluator reads, so a multi-repo
session is scored on every repo it touched instead of only the cwd's.

Every git call here goes through discover_repos._git, the hardened chokepoint that
neutralizes config-driven code execution (core.fsmonitor/pager, global/system config).
Repo roots and base refs both come from a user-confirmed selection file, but the repo's
.git/config itself is still attacker-controlled content on disk — an unhardened `git diff`
over it would re-open the exact RCE vector discover_repos.py closed. Import, don't reinvent.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))  # noqa: E402
from discover_repos import _git  # noqa: E402

STAT_LINE_LIMIT = 200
EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def _resolve_base(repo_root, base):
    """Resolve base to a commit SHA, or None if it doesn't name a commit here.

    The empty-tree SHA is a real, permanent git object (not a commit) that every repo
    has — it's the documented idiom for "diff everything as new". `^{commit}` would
    reject it, so it's verified against `^{tree}` instead; anything else must resolve
    to a commit, since a diff base that isn't a commit has no meaningful "before".
    """
    if base == EMPTY_TREE_SHA:
        return _git(["rev-parse", "--verify", "{}^{{tree}}".format(base)], repo_root)
    return _git(["rev-parse", "--verify", "{}^{{commit}}".format(base)], repo_root)


def _parse_numstat(numstat_text):
    """Parse `git diff --numstat` output into (insertions, deletions, files).

    Binary files report `-\t-\t<path>` for both counts — git can't diffstat them
    line-by-line. We still count the file as changed (Sensor: a binary asset changing
    must be visible to risk analysis) but contribute 0 to the insertion/deletion totals,
    since "-" has no numeric meaning to sum.
    """
    insertions = 0
    deletions = 0
    files = []
    for line in numstat_text.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        added, removed, path = parts
        files.append(path)
        if added != "-":
            insertions += int(added)
        if removed != "-":
            deletions += int(removed)
    return insertions, deletions, files


def _truncate_stat(stat_text):
    lines = stat_text.splitlines()
    if len(lines) <= STAT_LINE_LIMIT:
        return stat_text
    kept = lines[:STAT_LINE_LIMIT]
    kept.append("... (truncated, {} more lines)".format(len(lines) - STAT_LINE_LIMIT))
    return "\n".join(kept)


def _diff_one(repo_root, base):
    """Diff base -> working tree for one repo. Returns a repos-entry dict or raises ValueError."""
    if _git(["rev-parse", "--show-toplevel"], repo_root) is None:
        raise ValueError("not a git repo: {}".format(repo_root))

    base_resolved = _resolve_base(repo_root, base)
    if base_resolved is None:
        raise ValueError("base ref not found: {}".format(base))

    numstat = _git(["diff", "--numstat", base], repo_root)
    if numstat is None:
        raise ValueError("git diff --numstat failed against base: {}".format(base))
    insertions, deletions, files = _parse_numstat(numstat)

    stat = _git(["diff", "--stat", base], repo_root) or ""
    branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], repo_root) or ""

    return {
        "repoRoot": repo_root,
        "branch": branch,
        "base": base,
        "baseResolved": base_resolved,
        "insertions": insertions,
        "deletions": deletions,
        "filesChanged": len(files),
        "files": files,
        "stat": _truncate_stat(stat),
    }


def compute(pack_dir, selection):
    """Compute repo-diffs.json's content dict from a user-confirmed selection spec."""
    repos, skipped, errors = [], [], []
    for entry in selection.get("repos") or []:
        repo_root = entry.get("repoRoot")
        if entry.get("skip"):
            skipped.append({"repoRoot": repo_root, "reason": "user skipped"})
            continue
        try:
            repos.append(_diff_one(repo_root, entry.get("base")))
        except ValueError as exc:
            errors.append({"repoRoot": repo_root, "base": entry.get("base"), "error": str(exc)})
    return {"repos": repos, "skipped": skipped, "errors": errors}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Compute per-repo diffs vs a user-confirmed base for each repo a session touched")
    parser.add_argument("pack_dir")
    parser.add_argument("--selection", required=True, help="path to selection.json")
    args = parser.parse_args(argv)

    selection = json.loads(Path(args.selection).read_text(encoding="utf-8"))
    out = compute(args.pack_dir, selection)

    pack = Path(args.pack_dir)
    pack.mkdir(parents=True, exist_ok=True)
    (pack / "repo-diffs.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("repo-diffs.json: {} repos, {} skipped, {} errors".format(
        len(out["repos"]), len(out["skipped"]), len(out["errors"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
