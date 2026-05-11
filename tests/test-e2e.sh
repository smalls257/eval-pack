#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TEST_DIR=$(mktemp -d)
SESSION_ID="test-session-$(date +%s)"

trap 'rm -rf "$TEST_DIR"' EXIT

echo "=== Eval Pack E2E Test ==="
echo "Plugin root: $PLUGIN_ROOT"
echo "Test dir: $TEST_DIR"
echo "Session ID: $SESSION_ID"
echo ""

# Setup: create test transcript
mkdir -p "$TEST_DIR/$SESSION_ID"
cat > "$TEST_DIR/transcript.jsonl" << 'JSONL'
{"type":"human","timestamp":"2026-05-10T10:00:00Z","content":"Fix the auth bug in login.ts"}
{"type":"assistant","timestamp":"2026-05-10T10:01:00Z","model":"claude-opus-4-6","usage":{"input_tokens":1200,"output_tokens":800},"content":"I'll look at the auth bug. Let me read login.ts first."}
{"type":"human","timestamp":"2026-05-10T10:03:00Z","content":"The token expiry check is wrong"}
{"type":"assistant","timestamp":"2026-05-10T10:04:00Z","model":"claude-opus-4-6","usage":{"input_tokens":1500,"output_tokens":1000},"content":"Found it. The comparison uses < instead of <=. Let me fix that and run the tests."}
{"type":"assistant","timestamp":"2026-05-10T10:06:00Z","model":"claude-opus-4-6","usage":{"input_tokens":800,"output_tokens":600},"content":"Done. All tests pass now."}
{"type":"human","timestamp":"2026-05-10T10:07:00Z","content":"Actually the test for edge case is still failing"}
{"type":"assistant","timestamp":"2026-05-10T10:08:00Z","model":"claude-opus-4-6","usage":{"input_tokens":900,"output_tokens":700},"content":"Let me try again with the edge case. I see the issue — the boundary condition at midnight."}
{"type":"assistant","timestamp":"2026-05-10T10:10:00Z","model":"claude-opus-4-6","usage":{"input_tokens":600,"output_tokens":500},"content":"Fixed. All tests pass including the midnight edge case."}
JSONL

# Step 1: Extract metrics
echo "--- Step 1: Extract metrics ---"
"$PLUGIN_ROOT/scripts/extract-metrics.sh" "$TEST_DIR/transcript.jsonl" "$TEST_DIR/$SESSION_ID"

if [[ ! -f "$TEST_DIR/$SESSION_ID/metrics.json" ]]; then
  echo "FAIL: metrics.json not created" >&2
  exit 1
fi

MODEL=$(jq -r '.lastModel' "$TEST_DIR/$SESSION_ID/metrics.json")
TOKENS=$(jq '.totalTokens' "$TEST_DIR/$SESSION_ID/metrics.json")
TURNS=$(jq '.turnCount' "$TEST_DIR/$SESSION_ID/metrics.json")

echo "  lastModel: $MODEL"
echo "  Total tokens: $TOKENS"
echo "  Turn count: $TURNS"

if [[ "$TOKENS" -lt 1 ]]; then
  echo "FAIL: total tokens should be > 0" >&2
  exit 1
fi
echo "  PASS"

# Step 2: Detect patterns
echo ""
echo "--- Step 2: Detect patterns ---"
"$PLUGIN_ROOT/scripts/detect-patterns.sh" "$TEST_DIR/transcript.jsonl" "$TEST_DIR/$SESSION_ID"

if [[ ! -f "$TEST_DIR/$SESSION_ID/patterns.json" ]]; then
  echo "FAIL: patterns.json not created" >&2
  exit 1
fi

FALSE_COMP=$(jq '.falseCompletions | length' "$TEST_DIR/$SESSION_ID/patterns.json")
FLAGS=$(jq '.flags | length' "$TEST_DIR/$SESSION_ID/patterns.json")

echo "  False completions: $FALSE_COMP"
echo "  Flags: $FLAGS"

if [[ "$FALSE_COMP" -lt 1 ]]; then
  echo "FAIL: should detect false completion (agent said 'Done' then user corrected)" >&2
  exit 1
fi
echo "  PASS"

# Step 3: Create mock test results
echo ""
echo "--- Step 3: Mock test results ---"
cat > "$TEST_DIR/$SESSION_ID/test-results.json" << 'JSON'
{
  "verdict": "pass",
  "summary": "8 tests passed",
  "testsRun": [
    {"name": "auth.test.ts", "passed": true, "output": "8 passed"}
  ]
}
JSON
echo "  PASS"

# Step 4: Create mock analysis
echo ""
echo "--- Step 4: Mock analysis ---"
cat > "$TEST_DIR/$SESSION_ID/analysis.json" << 'JSON'
{
  "retrospective": "Session was efficient overall. One false completion where the agent claimed tests passed but an edge case was still failing.",
  "friction": "No type annotations on the auth module made it harder to understand token expiry logic.",
  "promptQuality": "Developer provided good initial context by naming the specific file. Could have mentioned the edge case upfront."
}
JSON
echo "  PASS"

# Step 5: Render HTML
echo ""
echo "--- Step 5: Render HTML ---"
"$PLUGIN_ROOT/scripts/render-html.sh" "$TEST_DIR" "$SESSION_ID" "$PLUGIN_ROOT" "$TEST_DIR/transcript.jsonl"

EXPECTED_FILES=("index.html" "styles.css" "scripts.js" "data.json" "transcript.jsonl")
for f in "${EXPECTED_FILES[@]}"; do
  if [[ ! -f "$TEST_DIR/$SESSION_ID/$f" ]]; then
    echo "FAIL: $f not found in pack" >&2
    exit 1
  fi
done

# Verify data.json structure
ROUNDS=$(jq '.rounds | length' "$TEST_DIR/$SESSION_ID/data.json")
HAS_TRANSCRIPT=$(jq '.transcript | length' "$TEST_DIR/$SESSION_ID/data.json")

echo "  Rounds: $ROUNDS"
echo "  Transcript entries: $HAS_TRANSCRIPT"

if [[ "$ROUNDS" -ne 1 ]]; then
  echo "FAIL: should have exactly 1 round" >&2
  exit 1
fi
echo "  PASS"

# Step 6: Test regeneration (round 2)
echo ""
echo "--- Step 6: Test regeneration (round 2) ---"
"$PLUGIN_ROOT/scripts/render-html.sh" "$TEST_DIR" "$SESSION_ID" "$PLUGIN_ROOT" "$TEST_DIR/transcript.jsonl"

ROUNDS=$(jq '.rounds | length' "$TEST_DIR/$SESSION_ID/data.json")
echo "  Rounds after regeneration: $ROUNDS"

if [[ "$ROUNDS" -ne 2 ]]; then
  echo "FAIL: should have 2 rounds after regeneration" >&2
  exit 1
fi
echo "  PASS"

echo ""
echo "=== ALL TESTS PASSED ==="
