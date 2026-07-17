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
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))  # noqa: E402
from discover_repos import _git, _git_argv, _hardened_env, GIT_TIMEOUT_SECS  # noqa: E402

STAT_LINE_LIMIT = 200
EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def _git_bytes(args, cwd):
    """Hardened git that returns RAW stdout bytes (or None on failure).

    Text `_git` decodes-and-strips, which corrupts a `--numstat -z` NUL stream
    (it eats the trailing NUL and can mangle non-UTF-8 path bytes). We still route
    through discover_repos's `_git_argv` + `_hardened_env` so the same config-driven
    code-exec neutralization applies — only the decode step differs. Reinventing the
    argv/env here would reopen the hole; borrowing them keeps one boundary.
    """
    try:
        out = subprocess.run(
            _git_argv(args, cwd),
            capture_output=True, timeout=GIT_TIMEOUT_SECS, env=_hardened_env(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    return out.stdout


_C_ESCAPES = {
    ord("t"): 0x09, ord("n"): 0x0A, ord("r"): 0x0D, ord("f"): 0x0C,
    ord("b"): 0x08, ord("v"): 0x0B, ord("a"): 0x07,
    ord("\\"): 0x5C, ord('"'): 0x22,
}


def _unquote_path_bytes(field):
    """Decode git's C-style path escaping on RAW bytes, returning a str.

    Under `-z` git omits wrapping quotes and leaves printable/unicode bytes raw, but
    STILL backslash-escapes genuine control chars (tab \\t, newline \\n) and non-ASCII
    via octal (\\NNN) unless core.quotePath is off. A field with no backslash is already
    the real path. We unescape at the BYTE level — decoding with unicode_escape on a str
    would misread multi-byte UTF-8 (café) as latin-1 — then decode UTF-8 once at the end.
    Leaving this un-decoded would report a tab-bearing filename under a fake name: a Leaky
    Narrative of the on-disk truth that risk analysis then can't map back to a real file.
    """
    if b"\\" not in field:
        return field.decode("utf-8", "surrogateescape")
    out = bytearray()
    i = 0
    n = len(field)
    while i < n:
        c = field[i]
        if c != 0x5C or i + 1 >= n:  # not a backslash, or trailing backslash
            out.append(c)
            i += 1
            continue
        nxt = field[i + 1]
        if 0x30 <= nxt <= 0x37:  # octal escape \NNN
            j = i + 1
            digits = []
            while j < n and len(digits) < 3 and 0x30 <= field[j] <= 0x37:
                digits.append(field[j])
                j += 1
            out.append(int(bytes(digits), 8) & 0xFF)
            i = j
        elif nxt in _C_ESCAPES:
            out.append(_C_ESCAPES[nxt])
            i += 2
        else:  # unknown escape — keep the backslash literally
            out.append(c)
            i += 1
    return out.decode("utf-8", "surrogateescape")


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


def _parse_numstat_z(raw):
    """Parse `git diff --numstat -M -z` RAW bytes into (insertions, deletions, files).

    The `-z` stream is NUL-separated with two record shapes:
      normal: one field "<add>\\t<del>\\t<path>"
      rename: field "<add>\\t<del>\\t" (trailing tab, empty 3rd) THEN two more NUL-
              terminated fields <oldpath>\\0<newpath>. We record the NEW path — a rename
              is not a fabricated `{a => b}` path (that string is no file that exists).
    Binary files report `-\t-` for both counts (git can't line-diff them); we still count
    the file as changed (Sensor: a binary asset changing must be visible to risk analysis)
    but add 0 lines, since "-" has no numeric meaning to sum.
    """
    insertions = 0
    deletions = 0
    files = []
    fields = raw.split(b"\0")
    idx = 0
    while idx < len(fields):
        field = fields[idx]
        if not field:  # trailing empty field after final NUL
            idx += 1
            continue
        parts = field.split(b"\t", 2)
        if len(parts) != 3:
            idx += 1
            continue
        added, removed, path = parts
        if path == b"":  # rename: next two fields are old, new
            if idx + 2 < len(fields):
                path = fields[idx + 2]  # NEW path
                idx += 3
            else:
                idx += 1
                continue
        else:
            idx += 1
        files.append(_unquote_path_bytes(path))
        if added != b"-":
            insertions += int(added)
        if removed != b"-":
            deletions += int(removed)
    return insertions, deletions, files


def _count_text_lines(repo_root, rel_path):
    """Added-line count for an untracked file: NUL byte => binary (0), else line count.

    Deterministic, no git, no index mutation. Binary files count as a changed file but
    contribute 0 lines (same rule as numstat's `-\t-`). Line count = number of '\\n', plus
    one if the file is non-empty and lacks a trailing newline (the last unterminated line).
    """
    try:
        data = (Path(repo_root) / rel_path).read_bytes()
    except OSError:
        return 0
    if b"\0" in data:
        return 0
    if not data:
        return 0
    lines = data.count(b"\n")
    if not data.endswith(b"\n"):
        lines += 1
    return lines


def _truncate_stat(stat_text):
    lines = stat_text.splitlines()
    if len(lines) <= STAT_LINE_LIMIT:
        return stat_text
    kept = lines[:STAT_LINE_LIMIT]
    kept.append("... (truncated, {} more lines)".format(len(lines) - STAT_LINE_LIMIT))
    return "\n".join(kept)


def _diff_one(repo_root, base):
    """Compute one repo's change surface. Returns a repos-entry dict or raises ValueError.

    The change surface reported is: base -> working tree for TRACKED files (committed +
    uncommitted, since the user's base is the "before"), PLUS untracked non-ignored files
    counted as additions by line count. Ignored files are excluded. Renames report the NEW
    path. The diff runs against the RESOLVED base SHA (not the raw ref string), so the
    reported baseResolved is definitionally what was diffed.
    """
    toplevel = _git(["rev-parse", "--show-toplevel"], repo_root)
    if toplevel is None:
        raise ValueError("not a git repo: {}".format(repo_root))
    # Emit git's canonical (symlink-resolved) root, not whatever form the selection
    # used. discovered-repos.json holds this same --show-toplevel value, so the coverage
    # gate's set match is over one path form — a raw /var vs /private/var selection can't
    # false-refuse a covered pack.
    repo_root = toplevel

    base_resolved = _resolve_base(repo_root, base)
    if base_resolved is None:
        raise ValueError("base ref not found: {}".format(base))

    numstat = _git_bytes(["diff", "--numstat", "-M", "-z", base_resolved], repo_root)
    if numstat is None:
        raise ValueError("git diff --numstat failed against base: {}".format(base))
    insertions, deletions, files = _parse_numstat_z(numstat)

    # Union in untracked (non-ignored) files — `git diff` is tracked-only, so a file the
    # session created but never `git add`ed vanishes. `ls-files --others` is NON-mutating
    # (it does NOT touch the user's index). Skip any path already counted as tracked so an
    # intent-to-add / edited-then-listed path isn't double counted.
    seen_files = set(files)
    others = _git(["ls-files", "--others", "--exclude-standard", "-z"], repo_root) or ""
    for path in (p for p in others.split("\0") if p):
        if path in seen_files:
            continue
        files.append(path)
        seen_files.add(path)
        insertions += _count_text_lines(repo_root, path)

    stat = _git(["diff", "--stat", base_resolved], repo_root) or ""
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
            # Canonicalize skipped roots too (they never touch git, so there's no
            # --show-toplevel to borrow) so a skipped repo also matches discovered.
            canon = os.path.realpath(repo_root).rstrip("/") if repo_root else repo_root
            skipped.append({"repoRoot": canon, "reason": "user skipped"})
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
