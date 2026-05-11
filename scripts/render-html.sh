#!/usr/bin/env bash
set -euo pipefail

OUTPUT_DIR="${1:?Usage: render-html.sh <output-dir> <session-id> <plugin-root> [transcript-file]}"
SESSION_ID="${2:?Usage: render-html.sh <output-dir> <session-id> <plugin-root> [transcript-file]}"
PLUGIN_ROOT="${3:?Usage: render-html.sh <output-dir> <session-id> <plugin-root> [transcript-file]}"
TRANSCRIPT_FILE="${4:-}"

PACK_DIR="$OUTPUT_DIR/$SESSION_ID"
TEMPLATE_DIR="$PLUGIN_ROOT/templates/html"

mkdir -p "$PACK_DIR/screenshots" "$PACK_DIR/logs"

# Copy HTML template files
cp "$TEMPLATE_DIR/index.html" "$PACK_DIR/index.html"
cp "$TEMPLATE_DIR/styles.css" "$PACK_DIR/styles.css"
cp "$TEMPLATE_DIR/scripts.js" "$PACK_DIR/scripts.js"

# Copy transcript if present
if [[ -n "$TRANSCRIPT_FILE" && -f "$TRANSCRIPT_FILE" ]]; then
  cp "$TRANSCRIPT_FILE" "$PACK_DIR/transcript.jsonl"
fi

# Build data.json from intermediate files
METRICS="{}"
PATTERNS="{}"
ANALYSIS="{}"
TRANSCRIPT="[]"
TEST_RESULTS="{}"
SCREENSHOTS="[]"

if [[ -f "$PACK_DIR/metrics.json" ]]; then
  METRICS=$(cat "$PACK_DIR/metrics.json")
fi

if [[ -f "$PACK_DIR/patterns.json" ]]; then
  PATTERNS=$(cat "$PACK_DIR/patterns.json")
fi

if [[ -f "$PACK_DIR/analysis.json" ]]; then
  ANALYSIS=$(cat "$PACK_DIR/analysis.json")
fi

if [[ -f "$PACK_DIR/test-results.json" ]]; then
  TEST_RESULTS=$(cat "$PACK_DIR/test-results.json")
fi

if [[ -f "$PACK_DIR/transcript.jsonl" ]]; then
  TRANSCRIPT=$(jq -s '.' "$PACK_DIR/transcript.jsonl")
fi

# Detect screenshots
if [[ -d "$PACK_DIR/screenshots" ]] && ls "$PACK_DIR/screenshots/"*.png >/dev/null 2>&1; then
  SCREENSHOTS=$(ls "$PACK_DIR/screenshots/"*.png | while read -r f; do
    basename=$(basename "$f" .png)
    label=$(echo "$basename" | tr '-' ' ' | tr '_' ' ')
    printf '{"path":"screenshots/%s","label":"%s"}\n' "$(basename "$f")" "$label"
  done | jq -s '.')
fi

# Check for existing data.json with rounds
EXISTING_ROUNDS="[]"
if [[ -f "$PACK_DIR/data.json" ]]; then
  EXISTING_ROUNDS=$(jq '.rounds // []' "$PACK_DIR/data.json")
fi

NEW_ROUND=$(jq -n \
  --argjson metrics "$METRICS" \
  --argjson patterns "$PATTERNS" \
  --argjson analysis "$ANALYSIS" \
  --argjson testResults "$TEST_RESULTS" \
  --argjson screenshots "$SCREENSHOTS" \
  '{
    metrics: $metrics,
    patterns: $patterns,
    analysis: $analysis,
    testResults: $testResults,
    screenshots: $screenshots,
    generatedAt: now | todate
  }')

ROUNDS=$(echo "$EXISTING_ROUNDS" | jq --argjson new "$NEW_ROUND" '. + [$new]')

jq -n \
  --arg sessionId "$SESSION_ID" \
  --arg generatedAt "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --argjson rounds "$ROUNDS" \
  --argjson transcript "$TRANSCRIPT" \
  '{
    sessionId: $sessionId,
    generatedAt: $generatedAt,
    rounds: $rounds,
    transcript: $transcript
  }' > "$PACK_DIR/data.json"

echo "Eval pack rendered to $PACK_DIR"
