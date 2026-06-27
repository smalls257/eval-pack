#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TEST_DIR=$(mktemp -d)
trap 'rm -rf "$TEST_DIR"' EXIT

echo "=== Phase 4 E2E (relevance + subagents) ==="

REPO="$TEST_DIR/repo"; mkdir -p "$REPO"
git -C "$REPO" init -q; git -C "$REPO" config user.email t@t.t; git -C "$REPO" config user.name t

CFG="$TEST_DIR/cfg"
SLUG=$(python3 -c "print('$REPO'.replace('/', '-'))")
PROJ="$CFG/projects/$SLUG"; mkdir -p "$PROJ"

# prior session on SAME branch (main), with a sub-agent
cat > "$PROJ/prior.jsonl" <<'JSONL'
{"type":"user","uuid":"p1","gitBranch":"main","timestamp":"2026-06-01T08:00:00Z","message":{"content":[{"type":"text","text":"prior same-branch work"}]}}
JSONL
mkdir -p "$PROJ/prior/subagents"
cat > "$PROJ/prior/subagents/agent-x.jsonl" <<'JSONL'
{"type":"assistant","uuid":"sa1","timestamp":"2026-06-01T08:30:00Z","message":{"content":[{"type":"text","text":"subagent did work"}]}}
JSONL

# prior session on OTHER branch
cat > "$PROJ/other.jsonl" <<'JSONL'
{"type":"user","uuid":"o1","gitBranch":"feature/z","timestamp":"2026-05-01T00:00:00Z","message":{"content":[{"type":"text","text":"unrelated branch"}]}}
JSONL

# CURRENT session (on main)
CUR="$TEST_DIR/cur.jsonl"
cat > "$CUR" <<'JSONL'
{"type":"user","uuid":"c1","gitBranch":"main","timestamp":"2026-06-02T08:00:00Z","message":{"content":"current"}}
JSONL

# 1. candidate list: prior is relevant (main), other is not (feature/z), current excluded
CANDS=$(cd "$REPO" && CLAUDE_CONFIG_DIR="$CFG" python3 "$PLUGIN_ROOT/scripts/list_candidates.py" "$REPO" "cur" "main")
echo "$CANDS" | python3 -c "
import json,sys
c={x['sessionId']:x for x in json.load(sys.stdin)}
assert 'cur' not in c, 'current must be excluded'
assert c['prior']['relevant'] is True, c['prior']
assert c['other']['relevant'] is False, c['other']
print('candidates OK: prior=relevant, other=not, current excluded')
"

# 2. simulate the user confirming ONLY the relevant prior session -> merge with subagents
PICK=$(echo "$CANDS" | python3 -c "import json,sys; print([x['transcriptPath'] for x in json.load(sys.stdin) if x['sessionId']=='prior'][0])")
OUT="$TEST_DIR/merged.jsonl"
( cd "$REPO" && python3 "$PLUGIN_ROOT/scripts/build_conversation.py" "$CUR" "cur" "$OUT" --select "$PICK" )

UUIDS=$(python3 -c "import json;print(','.join(json.loads(l)['uuid'] for l in open('$OUT') if l.strip()))")
if [[ "$UUIDS" != "p1,sa1,c1" ]]; then
  echo "FAIL: merged uuids were '$UUIDS', expected 'p1,sa1,c1'" >&2
  exit 1
fi

# 3. current-only when no selection (CI path)
OUT2="$TEST_DIR/merged2.jsonl"
( cd "$REPO" && python3 "$PLUGIN_ROOT/scripts/build_conversation.py" "$CUR" "cur" "$OUT2" )
U2=$(python3 -c "import json;print(','.join(json.loads(l)['uuid'] for l in open('$OUT2') if l.strip()))")
if [[ "$U2" != "c1" ]]; then
  echo "FAIL: no-selection merge was '$U2', expected 'c1'" >&2
  exit 1
fi

echo "=== PHASE 4 E2E PASSED (picked=$UUIDS, current-only=$U2) ==="
