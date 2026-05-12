#!/usr/bin/env bash
set -euo pipefail

if ! command -v python3 &>/dev/null; then
  echo "Error: python3 is required by render-html.sh but was not found. Install Python 3 and try again." >&2
  exit 1
fi

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

# Pull in any Playwright MCP screenshots from plugin root
PLAYWRIGHT_MCP_DIR="$PLUGIN_ROOT/.playwright-mcp"
if [[ -d "$PLAYWRIGHT_MCP_DIR" ]] && ls "$PLAYWRIGHT_MCP_DIR/"*.png >/dev/null 2>&1; then
  cp "$PLAYWRIGHT_MCP_DIR/"*.png "$PACK_DIR/screenshots/" 2>/dev/null || true
fi

# Detect screenshots — short list, safe as --argjson
SCREENSHOTS="[]"
if [[ -d "$PACK_DIR/screenshots" ]] && ls "$PACK_DIR/screenshots/"*.png >/dev/null 2>&1; then
  SCREENSHOTS=$(ls "$PACK_DIR/screenshots/"*.png | while read -r f; do
    stem=$(basename "$f" .png)
    label=$(echo "$stem" | tr '-' ' ' | tr '_' ' ')
    printf '{"path":"screenshots/%s","label":"%s"}\n' "$(basename "$f")" "$label"
  done | jq -s '.')
fi

# Capture git branch
GIT_BRANCH=$(git -C "$PLUGIN_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")

# Build new round using --slurpfile to avoid "argument list too long" for large JSON files
NEW_ROUND_TMP=$(mktemp)
jq -n \
  --slurpfile metrics     "$PACK_DIR/metrics.json" \
  --slurpfile patterns    "$PACK_DIR/patterns.json" \
  --slurpfile analysis    "$PACK_DIR/analysis.json" \
  --slurpfile testResults "$PACK_DIR/test-results.json" \
  --slurpfile tools       "$PACK_DIR/tools.json" \
  --argjson screenshots   "$SCREENSHOTS" \
  --arg     gitBranch     "$GIT_BRANCH" \
  '{
    metrics:     $metrics[0],
    patterns:    $patterns[0],
    analysis:    $analysis[0],
    testResults: $testResults[0],
    tools:       $tools[0],
    screenshots: $screenshots,
    gitBranch:   $gitBranch,
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

# Inline data.json into index.html so it opens without a server
DATA_JS="<script>window.__EVAL_PACK_DATA__ = $(cat "$PACK_DIR/data.json");</script>"
if grep -q '__EVAL_PACK_DATA__' "$PACK_DIR/index.html" 2>/dev/null; then
  # Replace existing inline data
  python3 -c "
import sys, re
html = open('$PACK_DIR/index.html').read()
data = open('$PACK_DIR/data.json').read()
html = re.sub(r'<script>window\.__EVAL_PACK_DATA__[^<]*</script>', '<script>window.__EVAL_PACK_DATA__ = ' + data + ';</script>', html)
open('$PACK_DIR/index.html', 'w').write(html)
"
else
  # Insert before </body>
  python3 -c "
import sys
html = open('$PACK_DIR/index.html').read()
data = open('$PACK_DIR/data.json').read()
tag = '<script>window.__EVAL_PACK_DATA__ = ' + data + ';</script>'
html = html.replace('</body>', tag + '\n</body>')
open('$PACK_DIR/index.html', 'w').write(html)
"
fi

echo "Eval pack rendered to $PACK_DIR"
