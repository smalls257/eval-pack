#!/usr/bin/env bash
set -euo pipefail

TRANSCRIPT_FILE="${1:?Usage: detect-patterns.sh <transcript.jsonl> <output-dir>}"
OUTPUT_DIR="${2:?Usage: detect-patterns.sh <transcript.jsonl> <output-dir>}"

mkdir -p "$OUTPUT_DIR"

if [[ ! -f "$TRANSCRIPT_FILE" ]]; then
  echo "Error: transcript file not found: $TRANSCRIPT_FILE" >&2
  exit 1
fi

TRANSCRIPT=$(jq -s '.' "$TRANSCRIPT_FILE")

# False completions: assistant says done/complete/finished, then human responds with correction
FALSE_COMPLETIONS=$(echo "$TRANSCRIPT" | jq '
  . as $arr |
  [range(0; ($arr | length) - 1) |
    . as $i |
    if ($arr[$i].type == "assistant" and $arr[$i+1].type == "human") then
      if (($arr[$i].content | test("(?i)(done|complete|finished|all set|that should|looks good now)")) and
          ($arr[$i+1].content | test("(?i)(no|not|wrong|still|actually|but|fix|fail|error|broken|issue)"))) then
        {
          turn: $i,
          agentClaim: ($arr[$i].content | .[0:120]),
          userResponse: ($arr[$i+1].content | .[0:120])
        }
      else empty end
    else empty end
  ]
')

# Retry patterns: assistant attempts same tool/action multiple times
RETRY_COUNT=$(echo "$TRANSCRIPT" | jq '
  [.[] | select(.type == "assistant") |
    .content | tostring |
    select(test("(?i)(try again|retry|let me try|another approach|different approach)"))
  ] | length
')

# Test failures during session
TEST_FAILURES=$(echo "$TRANSCRIPT" | jq '
  [.[] | select(.type == "assistant") |
    .content | tostring |
    select(test("(?i)(FAIL|test failed|tests? failing|assertion.?error|expect.* to |error:.*test)"))
  ] | length
')

# Scope drift: count unique file paths mentioned in tool use
SCOPE_DRIFT="false"
if [[ -f "$OUTPUT_DIR/metrics.json" ]]; then
  FILE_COUNT=$(jq '.filesChanged // 0' "$OUTPUT_DIR/metrics.json")
  if [[ "$FILE_COUNT" -gt 10 ]]; then
    SCOPE_DRIFT="true"
  fi
fi

jq -n \
  --argjson false_completions "$FALSE_COMPLETIONS" \
  --argjson retry_count "$RETRY_COUNT" \
  --argjson test_failures "$TEST_FAILURES" \
  --argjson scope_drift "$SCOPE_DRIFT" \
  '{
    falseCompletions: $false_completions,
    retryCount: $retry_count,
    testFailureCount: $test_failures,
    scopeDrift: $scope_drift,
    flags: [
      if ($test_failures > 0) then {level: "red", label: "Test failures during session", count: $test_failures} else empty end,
      if (($false_completions | length) > 0) then {level: "amber", label: "False completions", count: ($false_completions | length)} else empty end,
      if ($retry_count > 3) then {level: "amber", label: "High retry count", count: $retry_count} else empty end,
      if ($scope_drift) then {level: "amber", label: "Scope drift — many files changed"} else empty end,
      if ($test_failures == 0 and ($false_completions | length) == 0 and $retry_count <= 3 and ($scope_drift | not)) then {level: "green", label: "Clean first-pass implementation"} else empty end
    ]
  }' > "$OUTPUT_DIR/patterns.json"

echo "Patterns written to $OUTPUT_DIR/patterns.json"
