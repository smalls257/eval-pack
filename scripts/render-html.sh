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

# Copy transcript and extract tool usage if present
if [[ -n "$TRANSCRIPT_FILE" && -f "$TRANSCRIPT_FILE" ]]; then
  cp "$TRANSCRIPT_FILE" "$PACK_DIR/transcript.jsonl"
  "$PLUGIN_ROOT/scripts/extract-tools.sh" "$TRANSCRIPT_FILE" "$PACK_DIR" \
    || echo "Warning: extract-tools.sh failed; tool data will be empty" >&2
fi

# Write default intermediate files so --slurpfile always has a valid target
[[ -f "$PACK_DIR/metrics.json" ]]      || echo '{}' > "$PACK_DIR/metrics.json"
[[ -f "$PACK_DIR/patterns.json" ]]     || echo '{}' > "$PACK_DIR/patterns.json"
[[ -f "$PACK_DIR/analysis.json" ]]     || echo '{}' > "$PACK_DIR/analysis.json"
[[ -f "$PACK_DIR/test-results.json" ]] || echo '{}' > "$PACK_DIR/test-results.json"
[[ -f "$PACK_DIR/tools.json" ]]        || echo '{}' > "$PACK_DIR/tools.json"

# Detect screenshots — short list, safe as --argjson
SCREENSHOTS="[]"
if [[ -d "$PACK_DIR/screenshots" ]] && ls "$PACK_DIR/screenshots/"*.png >/dev/null 2>&1; then
  SCREENSHOTS=$(ls "$PACK_DIR/screenshots/"*.png | while read -r f; do
    stem=$(basename "$f" .png)
    label=$(echo "$stem" | tr '-' ' ' | tr '_' ' ')
    printf '{"path":"screenshots/%s","label":"%s"}\n' "$(basename "$f")" "$label"
  done | jq -s '.')
fi

# Build new round using --slurpfile to avoid "argument list too long" for large JSON files
NEW_ROUND_TMP=$(mktemp)
jq -n \
  --slurpfile metrics     "$PACK_DIR/metrics.json" \
  --slurpfile patterns    "$PACK_DIR/patterns.json" \
  --slurpfile analysis    "$PACK_DIR/analysis.json" \
  --slurpfile testResults "$PACK_DIR/test-results.json" \
  --slurpfile tools       "$PACK_DIR/tools.json" \
  --argjson screenshots   "$SCREENSHOTS" \
  '{
    metrics:     $metrics[0],
    patterns:    $patterns[0],
    analysis:    $analysis[0],
    testResults: $testResults[0],
    tools:       $tools[0],
    screenshots: $screenshots,
    generatedAt: now | todate
  }' > "$NEW_ROUND_TMP"

# Accumulate rounds — append new round to existing (supports regeneration)
ROUNDS_TMP=$(mktemp)
if [[ -f "$PACK_DIR/data.json" ]]; then
  jq --slurpfile new "$NEW_ROUND_TMP" '(.rounds // []) + $new' "$PACK_DIR/data.json" > "$ROUNDS_TMP"
else
  jq -s '.' "$NEW_ROUND_TMP" > "$ROUNDS_TMP"
fi

# Build data.json base (no transcript yet — transcript merged separately to avoid arg limits)
jq -n \
  --arg sessionId    "$SESSION_ID" \
  --arg generatedAt  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --slurpfile rounds "$ROUNDS_TMP" \
  '{
    sessionId:   $sessionId,
    generatedAt: $generatedAt,
    rounds:      $rounds[0],
    transcript:  []
  }' > "$PACK_DIR/data.json"

# Merge transcript from file — avoids arg-list limits on long sessions
if [[ -f "$PACK_DIR/transcript.jsonl" ]]; then
  TRANSCRIPT_TMP=$(mktemp)
  jq -s '.' "$PACK_DIR/transcript.jsonl" > "$TRANSCRIPT_TMP"
  jq --slurpfile tr "$TRANSCRIPT_TMP" '.transcript = $tr[0]' "$PACK_DIR/data.json" > "$PACK_DIR/data.json.tmp"
  mv "$PACK_DIR/data.json.tmp" "$PACK_DIR/data.json"
  rm -f "$TRANSCRIPT_TMP"
fi

rm -f "$NEW_ROUND_TMP" "$ROUNDS_TMP"

echo "Eval pack rendered to $PACK_DIR"
