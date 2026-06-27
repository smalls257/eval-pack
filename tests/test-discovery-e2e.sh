#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TEST_DIR=$(mktemp -d)
trap 'rm -rf "$TEST_DIR"' EXIT

echo "=== Discovery E2E ==="

REPO="$TEST_DIR/repo"
mkdir -p "$REPO"
git -C "$REPO" init -q
git -C "$REPO" config user.email t@t.t
git -C "$REPO" config user.name t

# A Claude Code transcript store with one session for this repo (never archived)
CFG="$TEST_DIR/cfg"
SLUG=$(python3 -c "print('$REPO'.replace('/', '-'))")
PROJ="$CFG/projects/$SLUG"
mkdir -p "$PROJ"
cat > "$PROJ/disc1.jsonl" <<'JSONL'
{"type":"user","uuid":"d1","gitBranch":"main","timestamp":"2026-06-01T08:00:00Z","message":{"content":[{"type":"text","text":"discovered work"}]}}
{"type":"assistant","uuid":"d2","timestamp":"2026-06-01T08:02:00Z","message":{"content":[{"type":"text","text":"ok"}]}}
JSONL

# discover_sessions must surface disc1
CANDS=$(cd "$REPO" && CLAUDE_CONFIG_DIR="$CFG" python3 "$PLUGIN_ROOT/scripts/discover_sessions.py" "$REPO")
echo "$CANDS" | python3 -c "import json,sys; c=json.load(sys.stdin); assert len(c)==1 and c[0]['sessionId']=='disc1', c; print('discovered:', c[0]['firstPrompt'])"

# Pick disc1 as an --extra and assemble alongside a current session
TR_CUR="$TEST_DIR/cur.jsonl"
cat > "$TR_CUR" <<'JSONL'
{"type":"user","uuid":"c1","gitBranch":"main","timestamp":"2026-06-02T08:00:00Z","message":{"content":"current"}}
JSONL
OUT="$TEST_DIR/merged.jsonl"
PICK=$(echo "$CANDS" | python3 -c "import json,sys; print(json.load(sys.stdin)[0]['transcriptPath'])")
( cd "$REPO" && python3 "$PLUGIN_ROOT/scripts/build_conversation.py" "$TR_CUR" "disccur" "$OUT" --select "$PICK" )

UUIDS=$(python3 -c "import json;print(','.join(json.loads(l)['uuid'] for l in open('$OUT') if l.strip()))")
if [[ "$UUIDS" != "d1,d2,c1" ]]; then
  echo "FAIL: merged uuids were '$UUIDS', expected 'd1,d2,c1'" >&2
  exit 1
fi

echo "=== DISCOVERY E2E PASSED (uuids=$UUIDS) ==="
