#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TEST_DIR=$(mktemp -d)
trap 'rm -rf "$TEST_DIR"' EXIT

echo "=== Whole-Conversation E2E ==="

REPO="$TEST_DIR/repo"
mkdir -p "$REPO"
git -C "$REPO" init -q
git -C "$REPO" config user.email t@t.t
git -C "$REPO" config user.name t

# Session A — archive it via the SessionEnd hook entrypoint
TR_A="$TEST_DIR/a.jsonl"
cat > "$TR_A" <<'JSONL'
{"type":"user","uuid":"a1","gitBranch":"feature/x","timestamp":"2026-06-01T10:00:00Z","message":{"content":"start work"}}
{"type":"assistant","uuid":"a2","timestamp":"2026-06-01T10:01:00Z","message":{"content":[{"type":"text","text":"done part one"}]}}
JSONL
echo "$(printf '{"session_id":"sessA","transcript_path":"%s","cwd":"%s","reason":"clear"}' "$TR_A" "$REPO")" \
  | python3 "$PLUGIN_ROOT/scripts/archive_session.py"

# Session B — the current live transcript, a different session
TR_B="$TEST_DIR/b.jsonl"
cat > "$TR_B" <<'JSONL'
{"type":"user","uuid":"b1","gitBranch":"feature/x","timestamp":"2026-06-02T09:00:00Z","message":{"content":"fix pr feedback"}}
{"type":"assistant","uuid":"b2","timestamp":"2026-06-02T09:05:00Z","message":{"content":[{"type":"text","text":"fixed"}]}}
JSONL

# Assemble the whole conversation from inside the repo
OUT="$TEST_DIR/merged.jsonl"
( cd "$REPO" && python3 "$PLUGIN_ROOT/scripts/build_conversation.py" "$REPO" "$TR_B" "$OUT" )

# The merged transcript must contain all four uuids, time-ordered a1,a2,b1,b2
UUIDS=$(python3 -c "import json,sys;print(','.join(json.loads(l)['uuid'] for l in open('$OUT') if l.strip()))")
if [[ "$UUIDS" != "a1,a2,b1,b2" ]]; then
  echo "FAIL: merged uuids were '$UUIDS', expected 'a1,a2,b1,b2'" >&2
  exit 1
fi

# Extraction over the merged transcript must see both sessions' turns
python3 "$PLUGIN_ROOT/scripts/extract_metrics.py" "$OUT" "$TEST_DIR/pack" >/dev/null
TURNS=$(python3 -c "import json;print(json.load(open('$TEST_DIR/pack/metrics.json'))['turnCount'])")
if [[ "$TURNS" -lt 2 ]]; then
  echo "FAIL: metrics turnCount over merged transcript was '$TURNS', expected >= 2" >&2
  exit 1
fi

echo "=== WHOLE-CONVERSATION E2E PASSED (uuids=$UUIDS, turns=$TURNS) ==="
