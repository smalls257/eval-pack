#!/usr/bin/env python3
"""Archive a Claude Code session transcript into the repo's eval-pack store.

Run as a plugin SessionEnd hook: reads the hook payload as JSON on stdin and
copies the session transcript to `<repo>/.eval-packs/sessions/<session-id>.jsonl`,
keyed by git repository identity so every subdirectory and linked worktree of
a repo archives into one place. Anchor: the conversation is preserved when the
session ends, before Claude Code's 30-day prune can erase it.
"""
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SESSIONS_DIRNAME = "sessions"
OUTPUT_DIRNAME = ".eval-packs"  # default outputDir; custom config not read by the hook


def resolve_repo_root(cwd):
    """Return the repo root for `cwd`, or None if cwd is not in a git repo.

    Uses the shared git common dir, which is identical for the main checkout
    and every linked worktree — so all worktrees of a repo map to one root.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(cwd), "rev-parse", "--git-common-dir"],
            capture_output=True, text=True,
        )
    except OSError:
        return None
    if out.returncode != 0:
        return None
    common = out.stdout.strip()
    if not common:
        return None
    p = Path(common)
    if not p.is_absolute():
        p = (Path(cwd) / p)
    p = p.resolve()
    return p.parent if p.name == ".git" else p


def archive_paths(repo_root):
    """Return (sessions_dir, index_path) under the repo's eval-pack store."""
    sessions_dir = Path(repo_root) / OUTPUT_DIRNAME / SESSIONS_DIRNAME
    return sessions_dir, sessions_dir / "index.json"


def _read_index(index_path):
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("sessions"), dict):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"sessions": {}}


def _branch_of(transcript_path):
    """Best-effort: the last gitBranch recorded in the transcript, else ''."""
    branch = ""
    try:
        with open(transcript_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("gitBranch"):
                    branch = entry["gitBranch"]
    except OSError:
        pass
    return branch


def archive_session(payload):
    """Archive one session from a SessionEnd-hook payload dict.

    Returns a status dict; never raises for expected conditions. Statuses:
    skipped-no-transcript, skipped-no-repo, archived.
    """
    session_id = payload.get("session_id") or ""
    transcript_path = payload.get("transcript_path") or ""
    cwd = payload.get("cwd") or "."
    if not session_id or not transcript_path:
        return {"status": "skipped-no-transcript"}
    src = Path(transcript_path)
    if not src.is_file():
        return {"status": "skipped-no-transcript"}

    repo_root = resolve_repo_root(cwd)
    if repo_root is None:
        return {"status": "skipped-no-repo"}

    sessions_dir, index_path = archive_paths(repo_root)
    sessions_dir.mkdir(parents=True, exist_ok=True)
    dest = sessions_dir / f"{session_id}.jsonl"
    shutil.copyfile(src, dest)

    index = _read_index(index_path)
    index["sessions"][session_id] = {
        "branch": _branch_of(src),
        "cwd": str(cwd),
        "capturedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
    return {"status": "archived", "dest": str(dest)}


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        print(f"eval-pack archive: invalid hook payload JSON: {exc}",
              file=sys.stderr)
        return 0
    try:
        result = archive_session(payload)
    except Exception as exc:  # never affect the session on an archive failure
        print(f"eval-pack archive: error: {exc}", file=sys.stderr)
        return 0
    if result["status"] != "archived":
        print(f"eval-pack archive: {result['status']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
