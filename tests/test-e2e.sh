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
{"type":"assistant","timestamp":"2026-05-10T10:01:00Z","message":{"model":"claude-opus-4-6","usage":{"input_tokens":1200,"output_tokens":800},"content":[{"type":"tool_use","name":"Read","id":"t1","input":{"file_path":"login.ts"}},{"type":"text","text":"Let me read login.ts first."}]}}
{"type":"user","timestamp":"2026-05-10T10:02:00Z","message":{"content":[{"type":"tool_result","tool_use_id":"t1","content":"export function checkExpiry(ts) { return ts < Date.now(); }"}]}}
{"type":"assistant","timestamp":"2026-05-10T10:03:00Z","message":{"model":"claude-opus-4-6","usage":{"input_tokens":1500,"output_tokens":1000},"content":[{"type":"tool_use","name":"Bash","id":"t2","input":{"command":"npm test"}},{"type":"text","text":"Running tests."}]}}
{"type":"user","timestamp":"2026-05-10T10:04:00Z","message":{"content":[{"type":"tool_result","tool_use_id":"t2","content":"PASS auth.test.ts"}]}}
{"type":"assistant","timestamp":"2026-05-10T10:06:00Z","message":{"model":"claude-opus-4-6","usage":{"input_tokens":800,"output_tokens":600},"content":[{"type":"text","text":"Done. All tests pass now."}]}}
{"type":"human","timestamp":"2026-05-10T10:07:00Z","content":"Actually the test for edge case is still failing"}
{"type":"assistant","timestamp":"2026-05-10T10:08:00Z","message":{"model":"claude-opus-4-6","usage":{"input_tokens":900,"output_tokens":700},"content":[{"type":"text","text":"Let me try again with the edge case. I see the issue — the boundary condition at midnight."}]}}
{"type":"assistant","timestamp":"2026-05-10T10:10:00Z","message":{"model":"claude-opus-4-6","usage":{"input_tokens":600,"output_tokens":500},"content":[{"type":"text","text":"Fixed. All tests pass including the midnight edge case."}]}}
JSONL

# Step 1: Extract metrics
echo "--- Step 1: Extract metrics ---"
python3 "$PLUGIN_ROOT/scripts/extract_metrics.py" "$TEST_DIR/transcript.jsonl" "$TEST_DIR/$SESSION_ID" \
  --insertions 10 \
  --deletions 3 \
  --files-changed 2 \
  --changed-files '["login.ts", "auth.test.ts"]'

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
python3 "$PLUGIN_ROOT/scripts/detect_patterns.py" "$TEST_DIR/transcript.jsonl" "$TEST_DIR/$SESSION_ID"

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

# Step 2.5: Extract tool usage
echo ""
echo "--- Step 2.5: Extract tool usage ---"
python3 "$PLUGIN_ROOT/scripts/extract_tools.py" "$TEST_DIR/transcript.jsonl" "$TEST_DIR/$SESSION_ID"

if [[ ! -f "$TEST_DIR/$SESSION_ID/tools.json" ]]; then
  echo "FAIL: tools.json not created" >&2
  exit 1
fi

TOOL_COUNT=$(jq '.toolCalls | length' "$TEST_DIR/$SESSION_ID/tools.json")
TOTAL_CALLS=$(jq '.totalToolCalls' "$TEST_DIR/$SESSION_ID/tools.json")
echo "  Distinct tools: $TOOL_COUNT"
echo "  Total tool calls: $TOTAL_CALLS"

if [[ "$TOOL_COUNT" -ne 2 ]]; then
  echo "FAIL: expected 2 distinct tools, got $TOOL_COUNT" >&2
  exit 1
fi

if [[ "$TOTAL_CALLS" -ne 2 ]]; then
  echo "FAIL: expected 2 total tool calls, got $TOTAL_CALLS" >&2
  exit 1
fi

READ_COUNT=$(jq '[.toolCalls[] | select(.name == "Read")] | length' "$TEST_DIR/$SESSION_ID/tools.json")
if [[ "$READ_COUNT" -ne 1 ]]; then
  echo "FAIL: expected Read tool in toolCalls" >&2
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
cp "$TEST_DIR/$SESSION_ID/analysis.json" "$TEST_DIR/analysis_backup.json"
echo "  PASS"

# Step 5: Render HTML
echo ""
echo "--- Step 5: Render HTML ---"
python3 "$PLUGIN_ROOT/scripts/render_html.py" "$TEST_DIR" "$SESSION_ID" "$PLUGIN_ROOT" "$TEST_DIR/transcript.jsonl" \
  --branch "test-branch"

ZIP_NAME="test-branch"
ZIP_PATH="$TEST_DIR/$ZIP_NAME.zip"

if [[ ! -f "$ZIP_PATH" ]]; then
  echo "FAIL: zip not found at $ZIP_PATH" >&2
  exit 1
fi

python3 - "$ZIP_PATH" "$SESSION_ID" << 'PYEOF'
import sys, zipfile, json

zip_path, session_id = sys.argv[1], sys.argv[2]
zf = zipfile.ZipFile(zip_path)
names = zf.namelist()

required = ["index.html", "styles.css", "scripts.js", "data.json"]
for f in required:
    if not any(n.endswith(f) for n in names):
        print(f"FAIL: {f} not found in zip", file=sys.stderr)
        sys.exit(1)

data_entry = next(n for n in names if n.endswith("data.json"))
data = json.loads(zf.read(data_entry))

for key in ("analysis", "metrics", "patterns", "tools"):
    if not data.get(key):
        print(f"FAIL: {key} should be at top level of data.json", file=sys.stderr)
        sys.exit(1)

rounds = data.get("rounds", [])
if len(rounds) != 1:
    print(f"FAIL: expected 1 round, got {len(rounds)}", file=sys.stderr)
    sys.exit(1)

for key in ("analysis", "metrics", "patterns", "tools"):
    if rounds[0].get(key):
        print(f"FAIL: {key} should not appear inside rounds", file=sys.stderr)
        sys.exit(1)

tools = data.get("tools", {}).get("toolCalls", [])
if not tools:
    print("FAIL: tools.toolCalls missing from top-level data.json", file=sys.stderr)
    sys.exit(1)

print(f"  Rounds: {len(rounds)}")
print(f"  Tools in data.json: {len(tools)} tool types")
print("  PASS")
PYEOF

# Step 6: Test regeneration (round 2)
echo ""
echo "--- Step 6: Test regeneration (round 2) ---"
# Recreate analysis.json — pack_dir was cleaned up after Step 5 zip
mkdir -p "$TEST_DIR/$SESSION_ID"
cp "$TEST_DIR/analysis_backup.json" "$TEST_DIR/$SESSION_ID/analysis.json"
python3 "$PLUGIN_ROOT/scripts/render_html.py" "$TEST_DIR" "$SESSION_ID" "$PLUGIN_ROOT" "$TEST_DIR/transcript.jsonl" \
  --branch "test-branch"

python3 - "$ZIP_PATH" << 'PYEOF'
import sys, zipfile, json

zf = zipfile.ZipFile(sys.argv[1])
data_entry = next(n for n in zf.namelist() if n.endswith("data.json"))
data = json.loads(zf.read(data_entry))
rounds = data.get("rounds", [])
if len(rounds) != 2:
    print(f"FAIL: expected 2 rounds after regeneration, got {len(rounds)}", file=sys.stderr)
    sys.exit(1)
print(f"  Rounds after regeneration: {len(rounds)}")
print("  PASS")
PYEOF

echo ""
echo "=== ALL TESTS PASSED ==="
