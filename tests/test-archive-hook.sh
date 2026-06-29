#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TEST_DIR=$(mktemp -d)
trap 'rm -rf "$TEST_DIR"' EXIT

echo "=== Archive Hook stdin Test ==="

# A real git repo so repo-identity resolution succeeds
REPO="$TEST_DIR/repo"
mkdir -p "$REPO"
git -C "$REPO" init -q
git -C "$REPO" config user.email t@t.t
git -C "$REPO" config user.name t

# A fake session transcript
TR="$TEST_DIR/session.jsonl"
cat > "$TR" <<'JSONL'
{"type":"user","uuid":"u1","gitBranch":"feature/x","timestamp":"2026-06-01T10:00:00Z","message":{"content":"hi"}}
{"type":"assistant","uuid":"u2","timestamp":"2026-06-01T10:01:00Z","message":{"content":[{"type":"text","text":"hello"}]}}
JSONL

# Drive the archiver exactly as the SessionEnd hook will: JSON on stdin
PAYLOAD=$(printf '{"session_id":"sess-abc","transcript_path":"%s","cwd":"%s","hook_event_name":"SessionEnd","reason":"other"}' "$TR" "$REPO")
echo "$PAYLOAD" | python3 "$PLUGIN_ROOT/scripts/archive_session.py"

DEST="$REPO/.eval-packs/sessions/sess-abc.jsonl"
if [[ ! -f "$DEST" ]]; then
  echo "FAIL: transcript not archived to $DEST" >&2
  exit 1
fi
if ! diff -q "$TR" "$DEST" >/dev/null; then
  echo "FAIL: archived copy differs from source" >&2
  exit 1
fi
BRANCH=$(python3 -c "import json;print(json.load(open('$REPO/.eval-packs/sessions/index.json'))['sessions']['sess-abc']['branch'])")
if [[ "$BRANCH" != "feature/x" ]]; then
  echo "FAIL: index branch was '$BRANCH', expected 'feature/x'" >&2
  exit 1
fi

# Not-a-repo payload must be a no-op (no archive store created)
NON_REPO="$TEST_DIR/plain"; mkdir -p "$NON_REPO"
PAYLOAD2=$(printf '{"session_id":"s2","transcript_path":"%s","cwd":"%s","reason":"other"}' "$TR" "$NON_REPO")
echo "$PAYLOAD2" | python3 "$PLUGIN_ROOT/scripts/archive_session.py"
if [[ -d "$NON_REPO/.eval-packs" ]]; then
  echo "FAIL: archived despite cwd not being a git repo" >&2
  exit 1
fi

echo "=== ARCHIVE HOOK TEST PASSED ==="
