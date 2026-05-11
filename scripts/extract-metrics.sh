#!/usr/bin/env bash
set -euo pipefail

TRANSCRIPT_FILE="${1:?Usage: extract-metrics.sh <transcript.jsonl> <output-dir>}"
OUTPUT_DIR="${2:?Usage: extract-metrics.sh <transcript.jsonl> <output-dir>}"

mkdir -p "$OUTPUT_DIR"

if [[ ! -f "$TRANSCRIPT_FILE" ]]; then
  echo "Error: transcript file not found: $TRANSCRIPT_FILE" >&2
  exit 1
fi

TURN_COUNT=$(jq -s '[.[] | select(.type == "user" or .type == "human" or .type == "assistant")] | length' "$TRANSCRIPT_FILE")

MODEL=$(jq -rs '[.[] | select(.type == "assistant") | (.message.model // .model) // empty] | last // "unknown"' "$TRANSCRIPT_FILE")

INPUT_TOKENS=$(jq -s '[.[] | select(.type == "assistant") | ((.message.usage // .usage).input_tokens // 0)] | add // 0' "$TRANSCRIPT_FILE")
OUTPUT_TOKENS=$(jq -s '[.[] | select(.type == "assistant") | ((.message.usage // .usage).output_tokens // 0)] | add // 0' "$TRANSCRIPT_FILE")
TOTAL_TOKENS=$((INPUT_TOKENS + OUTPUT_TOKENS))

FIRST_TS=$(jq -s '[.[] | .timestamp // empty] | first // null' "$TRANSCRIPT_FILE")
LAST_TS=$(jq -s '[.[] | .timestamp // empty] | last // null' "$TRANSCRIPT_FILE")

DIFF_STAT=""
if git rev-parse HEAD~1 >/dev/null 2>&1; then
  DIFF_STAT=$(git diff --stat HEAD~1 2>/dev/null || echo "")
fi
FILES_CHANGED=$(echo "$DIFF_STAT" | grep -c ' | ' || true)
INSERTIONS=$(echo "$DIFF_STAT" | tail -1 | grep -oE '[0-9]+ insertion' | grep -oE '[0-9]+' || true)
INSERTIONS=${INSERTIONS:-0}
DELETIONS=$(echo "$DIFF_STAT" | tail -1 | grep -oE '[0-9]+ deletion' | grep -oE '[0-9]+' || true)
DELETIONS=${DELETIONS:-0}

CHANGED_FILES=$(git diff --name-only HEAD~1 2>/dev/null | jq -R -s 'split("\n") | map(select(. != ""))')

jq -n \
  --arg model "$MODEL" \
  --argjson input_tokens "$INPUT_TOKENS" \
  --argjson output_tokens "$OUTPUT_TOKENS" \
  --argjson total_tokens "$TOTAL_TOKENS" \
  --argjson turn_count "$TURN_COUNT" \
  --argjson first_ts "$FIRST_TS" \
  --argjson last_ts "$LAST_TS" \
  --argjson files_changed "$FILES_CHANGED" \
  --argjson insertions "${INSERTIONS:-0}" \
  --argjson deletions "${DELETIONS:-0}" \
  --argjson changed_files "$CHANGED_FILES" \
  '{
    lastModel: $model,
    inputTokens: $input_tokens,
    outputTokens: $output_tokens,
    totalTokens: $total_tokens,
    turnCount: $turn_count,
    firstTimestamp: $first_ts,
    lastTimestamp: $last_ts,
    filesChanged: $files_changed,
    insertions: $insertions,
    deletions: $deletions,
    changedFilesList: $changed_files
  }' > "$OUTPUT_DIR/metrics.json"

echo "Metrics written to $OUTPUT_DIR/metrics.json"
