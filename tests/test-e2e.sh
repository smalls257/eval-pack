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
  "title": "Fix auth token expiry edge case in login.ts",
  "highlights": {
    "completionStatus": { "label": "Complete", "color": "green", "notes": "Bug fixed and all tests pass including midnight edge case" },
    "bestProof": { "badges": ["Passing Tests"], "note": "All 8 tests in auth.test.ts passed after fix" },
    "strongestEvidence": "Test suite output showing 8/8 pass after boundary condition fix",
    "mainRisk": "No integration test covering the token refresh path under load"
  },
  "summary": {
    "whatChanged": ["Fixed < to <= in token expiry comparison in login.ts", "Added boundary condition handling for midnight edge case"],
    "whatTranscriptProves": ["Agent identified root cause correctly on first read", "False completion detected — agent claimed done before edge case was fixed"],
    "whatStillNotProven": ["No load test for concurrent token refresh", "Only unit tests run, no e2e auth flow"]
  },
  "proof": {
    "artifactInventory": [
      {"name": "Transcript", "path": "transcript.jsonl", "type": "transcript", "description": "Primary source for commands, failures, and outputs"}
    ],
    "evidenceTable": [
      {"point": "Bug root cause identified", "where": "turn 4: agent identifies < vs <= comparison", "whyItMatters": "Shows agent understood the problem correctly"},
      {"point": "False completion", "where": "turn 5: agent said Done but edge case still failed", "whyItMatters": "Demonstrates need for edge case tests in spec"}
    ],
    "transcriptExcerpts": ["Found it. The comparison uses < instead of <=.", "Fixed. All tests pass including the midnight edge case."]
  },
  "testsExisting": {
    "narrative": "auth.test.ts covered the main token expiry path but lacked a boundary test for midnight. The edge case test was identified by the user, not the agent.",
    "validationTable": [
      {"validation": "auth.test.ts", "observedResult": "8 passed", "interpretation": "All existing tests plus new edge case pass"}
    ],
    "coveredWell": ["Standard token expiry", "Invalid token rejection"],
    "notCovered": ["Concurrent refresh", "Token refresh under network failure"]
  },
  "testsNew": {
    "narrative": "No new test files were added. The midnight edge case was covered by an existing parameterized test that was previously skipped.",
    "newTests": []
  },
  "frictionLog": [
    {"friction": "Missing boundary test for midnight edge case", "evidence": "User had to point out the failing edge case after agent claimed completion", "type": "docs", "resolution": "Edge case fixed, but test was user-identified not agent-identified"}
  ],
  "diff": {
    "artifactStatus": { "hasDiffStat": false, "hasDiffPatch": false, "note": "No diff artifacts captured in this test run" },
    "filesChanged": [{"file": "login.ts", "description": "Fixed token expiry comparison operator"}],
    "changeTable": [{"area": "Token expiry logic", "evidenceInTranscript": "The comparison uses < instead of <=", "observedEffect": "Tokens expiring exactly at boundary are now correctly rejected"}],
    "representativeCommands": []
  },
  "repoImprovements": [
    {"title": "Add boundary tests to auth module", "detail": "The auth.test.ts file lacks explicit boundary tests for token expiry timestamps. Add parameterized tests covering exactly-at-expiry, one-second-before, and one-second-after cases."}
  ],
  "userImprovements": [
    {"title": "Front-load edge case context in prompts", "detail": "The developer knew about the midnight edge case but did not mention it in the initial prompt. Including known edge cases upfront would have prevented the false completion."}
  ],
  "promptPattern": "Fix the token expiry check in login.ts — the < vs <= comparison is wrong. Known edge case: tokens expiring exactly at midnight should be rejected. Run auth.test.ts to verify.",
  "sessionArtifacts": [
    {"name": "Transcript", "path": "transcript.jsonl", "description": "Full session conversation in JSONL format"}
  ],
  "verdictStatement": "The auth token boundary fix is correctly implemented and verified by the test suite, though the false completion pattern indicates the agent should run edge case tests proactively before claiming completion."
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
