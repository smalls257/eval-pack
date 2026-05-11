#!/usr/bin/env bash
set -euo pipefail

TRANSCRIPT_FILE="${1:?Usage: extract-tools.sh <transcript.jsonl> <output-dir>}"
OUTPUT_DIR="${2:?Usage: extract-tools.sh <transcript.jsonl> <output-dir>}"

mkdir -p "$OUTPUT_DIR"

if [[ ! -f "$TRANSCRIPT_FILE" ]]; then
  echo "Error: transcript file not found: $TRANSCRIPT_FILE" >&2
  exit 1
fi

# Extract all tool_use blocks from both real CC format (.message.content[]) and flat format (.content[])
TOOL_CALLS_TMP=$(mktemp)
trap 'rm -f "$TOOL_CALLS_TMP"' EXIT
jq -s '[.[] |
  (.message.content // .content // []) |
  if type == "array" then .[] else empty end |
  select(.type == "tool_use")
]' "$TRANSCRIPT_FILE" > "$TOOL_CALLS_TMP"

# Tool call counts sorted descending
TOOL_COUNTS=$(jq '[group_by(.name)[] | {name: .[0].name, count: length}] | sort_by(-.count)' "$TOOL_CALLS_TMP")

# Total
TOTAL=$(jq 'length' "$TOOL_CALLS_TMP")

# Subagents (Agent tool dispatches)
SUBAGENTS=$(jq '[.[] | select(.name == "Agent") | {
  description: (.input.description // ""),
  model: (.input.model // "default"),
  subagentType: (.input.subagent_type // "general-purpose")
}]' "$TOOL_CALLS_TMP")

# Skills (Skill tool invocations) — deduplicated by name
SKILLS=$(jq '[.[] | select(.name == "Skill") | {
  name: (.input.skill // ""),
  args: ((.input.args // "") | .[0:200])
}] | unique_by(.name)' "$TOOL_CALLS_TMP")

jq -n \
  --argjson toolCalls      "$TOOL_COUNTS" \
  --argjson totalToolCalls "$TOTAL" \
  --argjson subagents      "$SUBAGENTS" \
  --argjson skills         "$SKILLS" \
  '{
    toolCalls:      $toolCalls,
    totalToolCalls: $totalToolCalls,
    subagents:      $subagents,
    skills:         $skills
  }' > "$OUTPUT_DIR/tools.json"

rm -f "$TOOL_CALLS_TMP"
echo "Tools written to $OUTPUT_DIR/tools.json"
