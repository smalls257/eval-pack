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
    "confidencePercent": 90,
    "confidenceNotes": "Test suite output showing 8/8 pass after boundary condition fix; no integration test covering the token refresh path under load"
  },
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
  --branch "test-branch" --open-base "$TEST_DIR/open"

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

# Step 5b: openable copy exists outside repo, zip still present, jsonl excluded
echo ""
echo "--- Step 5b: Openable dashboard copy ---"
OPEN_DIR="$TEST_DIR/open/eval-pack-$SESSION_ID"
if [[ ! -f "$OPEN_DIR/index.html" ]]; then
  echo "FAIL: openable index.html not found at $OPEN_DIR" >&2
  exit 1
fi
if ! grep -q "__EVAL_PACK_DATA__" "$OPEN_DIR/index.html"; then
  echo "FAIL: openable index.html missing embedded data" >&2
  exit 1
fi
# includeTranscript defaults to true -> the raw transcript.jsonl is bundled
if [[ ! -f "$OPEN_DIR/transcript.jsonl" ]]; then
  echo "FAIL: transcript.jsonl should be included in openable copy (includeTranscript default true)" >&2
  exit 1
fi
# Capture first (avoid SIGPIPE: grep -q closing the pipe early would fail unzip under pipefail)
ZIP_LIST=$(unzip -Z1 "$ZIP_PATH")
if ! printf '%s\n' "$ZIP_LIST" | grep -q "transcript.jsonl"; then
  echo "FAIL: transcript.jsonl should be bundled in the zip (includeTranscript default true)" >&2
  exit 1
fi
if [[ ! -f "$ZIP_PATH" ]]; then
  echo "FAIL: zip should still exist alongside openable copy" >&2
  exit 1
fi
echo "  PASS"

# Step 6: Test regeneration (round 2)
echo ""
echo "--- Step 6: Test regeneration (round 2) ---"
# Regeneration re-runs the full pipeline — pack_dir was cleaned up after Step 5.
# Recreate metrics (validation gate requires it) and analysis before rendering.
mkdir -p "$TEST_DIR/$SESSION_ID"
python3 "$PLUGIN_ROOT/scripts/extract_metrics.py" "$TEST_DIR/transcript.jsonl" "$TEST_DIR/$SESSION_ID"
cp "$TEST_DIR/analysis_backup.json" "$TEST_DIR/$SESSION_ID/analysis.json"
python3 "$PLUGIN_ROOT/scripts/render_html.py" "$TEST_DIR" "$SESSION_ID" "$PLUGIN_ROOT" "$TEST_DIR/transcript.jsonl" \
  --branch "test-branch" --open-base "$TEST_DIR/open"

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

# Step 7: disabled analysis renders honestly (no hard-fail, no fake score)
echo ""
echo "--- Step 7: Disabled analysis ---"
# Note: asserts the disabled flag round-trips into data.json (data contract).
# The browser-side banner/verdict toggle is JS and is not exercised headlessly here.
rm -rf "$TEST_DIR/$SESSION_ID"
mkdir -p "$TEST_DIR/$SESSION_ID"
python3 "$PLUGIN_ROOT/scripts/extract_metrics.py" "$TEST_DIR/transcript.jsonl" "$TEST_DIR/$SESSION_ID"
echo '{"title":"Disabled run","disabled":true}' > "$TEST_DIR/$SESSION_ID/analysis.json"
python3 "$PLUGIN_ROOT/scripts/render_html.py" "$TEST_DIR" "$SESSION_ID" "$PLUGIN_ROOT" "$TEST_DIR/transcript.jsonl" \
  --branch "test-branch" --open-base "$TEST_DIR/open"
DIS=$(jq '.analysis.disabled' "$TEST_DIR/open/eval-pack-$SESSION_ID/data.json")
if [[ "$DIS" != "true" ]]; then
  echo "FAIL: disabled flag should be carried into data.json, got $DIS" >&2
  exit 1
fi
echo "  PASS"

# Step 8: partial-session sensor — a transcript that starts mid-thread is flagged
echo ""
echo "--- Step 8: Partial session detection ---"
PART_DIR="$TEST_DIR/partial"
mkdir -p "$PART_DIR"
cat > "$TEST_DIR/partial-transcript.jsonl" << 'JSONL'
{"type":"user","uuid":"u1","parentUuid":"EXTERNAL-uuid-from-prior-file","timestamp":"2026-05-10T12:00:00Z","message":{"role":"user","content":"continue where we left off"}}
{"type":"assistant","uuid":"a1","parentUuid":"u1","timestamp":"2026-05-10T12:01:00Z","message":{"model":"claude-opus-4-6","usage":{"input_tokens":10,"output_tokens":10},"content":[{"type":"text","text":"Resuming."}]}}
JSONL
python3 "$PLUGIN_ROOT/scripts/detect_patterns.py" "$TEST_DIR/partial-transcript.jsonl" "$PART_DIR"
PARTIAL_FLAG=$(jq '[.flags[] | select(.label | startswith("Partial session"))] | length' "$PART_DIR/patterns.json")
if [[ "$PARTIAL_FLAG" -ne 1 ]]; then
  echo "FAIL: expected a 'Partial session' flag for a mid-thread transcript, got $PARTIAL_FLAG" >&2
  exit 1
fi
PSOBJ=$(jq '.partialSession.startsMidThread' "$PART_DIR/patterns.json")
if [[ "$PSOBJ" != "true" ]]; then
  echo "FAIL: partialSession.startsMidThread should be true, got $PSOBJ" >&2
  exit 1
fi
# Negative: the normal transcript (no parentUuids) must NOT be flagged partial
NEG_DIR="$TEST_DIR/negative"
mkdir -p "$NEG_DIR"
python3 "$PLUGIN_ROOT/scripts/detect_patterns.py" "$TEST_DIR/transcript.jsonl" "$NEG_DIR" 2>/dev/null
NEG=$(jq '[.flags[] | select(.label | startswith("Partial session"))] | length' "$NEG_DIR/patterns.json")
if [[ "$NEG" -ne 0 ]]; then
  echo "FAIL: normal transcript should not be flagged partial, got $NEG" >&2
  exit 1
fi
echo "  PASS"

# Step 9: screenshot provenance — agent / test / unknown sources land in data.json
echo ""
echo "--- Step 9: Screenshot provenance ---"
SS_SESSION="ss-provenance"
SS_PACK="$TEST_DIR/$SS_SESSION"
mkdir -p "$SS_PACK/screenshots"
echo '{"title":"Screenshot provenance test"}' > "$SS_PACK/analysis.json"
: > "$SS_PACK/screenshots/agent-shot.png"
: > "$SS_PACK/screenshots/test-shot.png"
: > "$SS_PACK/screenshots/mystery-shot.png"
echo '{"test-shot.png":"test"}' > "$SS_PACK/screenshots/sources.json"
cat > "$TEST_DIR/ss-transcript.jsonl" << 'JSONL'
{"type":"user","timestamp":"2026-05-10T09:59:00Z","message":{"content":"take a screenshot"}}
{"type":"assistant","timestamp":"2026-05-10T10:00:00Z","message":{"model":"x","content":[{"type":"tool_use","name":"mcp__playwright__browser_take_screenshot","id":"s1","input":{"filename":"agent-shot.png"}}]}}
JSONL
python3 "$PLUGIN_ROOT/scripts/extract_metrics.py" "$TEST_DIR/ss-transcript.jsonl" "$SS_PACK"
python3 "$PLUGIN_ROOT/scripts/render_html.py" "$TEST_DIR" "$SS_SESSION" "$PLUGIN_ROOT" "$TEST_DIR/ss-transcript.jsonl" \
  --branch "ss" --open-base "$TEST_DIR/open"
python3 - "$TEST_DIR/open/eval-pack-$SS_SESSION/data.json" << 'PY'
import json, sys
d = json.load(open(sys.argv[1]))
src = {s["path"].split("/")[-1]: s.get("source")
       for r in d.get("rounds", []) for s in (r.get("screenshots") or [])}
expected = {"agent-shot.png": "agent", "test-shot.png": "test", "mystery-shot.png": "unknown"}
for name, want in expected.items():
    if src.get(name) != want:
        print(f"FAIL: {name} source = {src.get(name)!r}, expected {want!r}", file=sys.stderr)
        sys.exit(1)
print("  screenshot sources:", src)
PY
echo "  PASS"

# Step 10: test flag is driven by the final verdict, not failure chatter
echo ""
echo "--- Step 10: Verdict-driven test flag ---"
VDIR="$TEST_DIR/verdict"
mkdir -p "$VDIR"
echo '{"verdict":"fail"}' > "$VDIR/test-results.json"
python3 "$PLUGIN_ROOT/scripts/detect_patterns.py" "$TEST_DIR/transcript.jsonl" "$VDIR"
RED=$(jq '[.flags[]|select(.label=="Tests failing at completion" and .level=="red")]|length' "$VDIR/patterns.json")
if [[ "$RED" -ne 1 ]]; then
  echo "FAIL: verdict 'fail' should give 1 red 'Tests failing at completion', got $RED" >&2; exit 1
fi
echo '{"verdict":"pass"}' > "$VDIR/test-results.json"
python3 "$PLUGIN_ROOT/scripts/detect_patterns.py" "$TEST_DIR/transcript.jsonl" "$VDIR"
GREEN=$(jq '[.flags[]|select(.label=="Tests passing at completion" and .level=="green")]|length' "$VDIR/patterns.json")
if [[ "$GREEN" -ne 1 ]]; then
  echo "FAIL: verdict 'pass' should give 1 green 'Tests passing at completion', got $GREEN" >&2; exit 1
fi
echo '{"verdict":"none"}' > "$VDIR/test-results.json"
python3 "$PLUGIN_ROOT/scripts/detect_patterns.py" "$TEST_DIR/transcript.jsonl" "$VDIR"
NONEC=$(jq '[.flags[]|select(.label|startswith("Tests "))]|length' "$VDIR/patterns.json")
if [[ "$NONEC" -ne 0 ]]; then
  echo "FAIL: verdict 'none' should give no 'Tests ...' flag, got $NONEC" >&2; exit 1
fi
rm -f "$VDIR/test-results.json"
python3 "$PLUGIN_ROOT/scripts/detect_patterns.py" "$TEST_DIR/transcript.jsonl" "$VDIR"
MISSING=$(jq '[.flags[]|select(.label|startswith("Tests "))]|length' "$VDIR/patterns.json")
if [[ "$MISSING" -ne 0 ]]; then
  echo "FAIL: missing test-results.json should give no 'Tests ...' flag, got $MISSING" >&2; exit 1
fi
echo "  PASS"

echo ""
echo "=== ALL TESTS PASSED ==="
