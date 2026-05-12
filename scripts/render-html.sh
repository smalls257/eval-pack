#!/usr/bin/env bash
set -euo pipefail

if ! command -v python3 &>/dev/null; then
  echo "Error: python3 is required by render-html.sh but was not found. Install Python 3 and try again." >&2
  exit 1
fi
if ! command -v jq &>/dev/null; then
  echo "Error: jq is required by render-html.sh but was not found. Install jq and try again." >&2
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

# Render transcript.html — conversational turns only (user text + assistant text + subagent dispatches)
if [[ -f "$PACK_DIR/transcript.jsonl" ]]; then
python3 -c "
import json, html as htmllib

rows = []
try:
    with open('$PACK_DIR/transcript.jsonl') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except Exception:
                continue
            role = e.get('type') or (e.get('message') or {}).get('role', '')
            msg = e.get('message') or e
            content = msg.get('content', '')
            ts = e.get('timestamp', '')[:19]

            if role in ('human', 'user'):
                # User message — plain text only
                text = content if isinstance(content, str) else ' '.join(
                    b.get('text', '') for b in content if isinstance(b, dict) and b.get('type') == 'text'
                ) if isinstance(content, list) else ''
                if not text.strip():
                    continue
                rows.append('<div class=\"turn user\"><div class=\"meta\">USER ' + htmllib.escape(ts) + '</div><pre>' + htmllib.escape(text) + '</pre></div>')

            elif role == 'assistant':
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    # Assistant text
                    if block.get('type') == 'text':
                        text = block.get('text', '').strip()
                        if text:
                            model = (msg.get('model') or '').upper()
                            rows.append('<div class=\"turn assistant\"><div class=\"meta\">' + htmllib.escape(model or 'ASSISTANT') + ' ' + htmllib.escape(ts) + '</div><pre>' + htmllib.escape(text) + '</pre></div>')
                    # Subagent dispatch — show description only
                    elif block.get('type') == 'tool_use' and block.get('name') == 'Agent':
                        desc = (block.get('input') or {}).get('description', '')
                        model = (block.get('input') or {}).get('model') or (block.get('input') or {}).get('subagent_type', '')
                        if desc:
                            rows.append('<div class=\"turn subagent\"><div class=\"meta\">→ SUBAGENT ' + htmllib.escape(ts) + '</div><pre>' + htmllib.escape(('[' + model + '] ' if model else '') + desc) + '</pre></div>')
except Exception as ex:
    rows.append('<div class=\"turn user\"><pre>Error rendering transcript: ' + htmllib.escape(str(ex)) + '</pre></div>')

page = '''<!DOCTYPE html><html><head><meta charset=\"utf-8\"><title>Transcript</title>
<style>
body{background:#0d0d1a;color:#ccc;font-family:monospace;font-size:13px;padding:16px;margin:0}
pre{white-space:pre-wrap;word-break:break-word;margin:4px 0}
.turn{margin:8px 0;border-left:3px solid #444;padding:8px 12px}
.user{background:#0f3460;border-color:#3a6ea5}
.assistant{background:#1a1a2e;border-color:#444}
.subagent{background:#1a2e1a;border-color:#3a7a3a}
.meta{font-size:11px;color:#888;margin-bottom:4px}
</style></head><body>''' + ''.join(rows) + '</body></html>'
open('$PACK_DIR/transcript.html', 'w').write(page)
"
fi

# Inline data into index.html — transcript stripped to keep file size small
python3 -c "
import re, json
html = open('$PACK_DIR/index.html').read()
data = json.loads(open('$PACK_DIR/data.json').read())
data['transcript'] = []
safe_data = json.dumps(data).replace('</', '<\\\\/')
tag = '<script>window.__EVAL_PACK_DATA__ = ' + safe_data + ';</script>'
if '__EVAL_PACK_DATA__' in html:
    html = re.sub(r'<script>window\.__EVAL_PACK_DATA__.*?</script>', tag, html, flags=re.DOTALL)
else:
    html = html.replace('<script src=\"scripts.js\">', tag + '\n  <script src=\"scripts.js\">')
open('$PACK_DIR/index.html', 'w').write(html)
open('$PACK_DIR/data.json', 'w').write(json.dumps(data))
"

# Zip the pack and remove the staging directory
(cd "$OUTPUT_DIR" && zip -9 -r "$SESSION_ID.zip" "$SESSION_ID/" -x "*.jsonl")
rm -rf "$PACK_DIR"

echo "Eval pack rendered to $OUTPUT_DIR/$SESSION_ID.zip"
