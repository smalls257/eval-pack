#!/usr/bin/env bash
set -euo pipefail

if ! command -v python3 &>/dev/null; then
  echo "Error: python3 is required by extract-metrics.sh but was not found. Install Python 3 and try again." >&2
  exit 1
fi
if ! command -v jq &>/dev/null; then
  echo "Error: jq is required by extract-metrics.sh but was not found. Install jq and try again." >&2
  exit 1
fi

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
TOKEN_BY_MODEL=$(jq -s '[.[] | select(.type == "assistant") | {model: ((.message.model // .model) // "unknown"), input: ((.message.usage // .usage).input_tokens // 0), output: ((.message.usage // .usage).output_tokens // 0)}] | group_by(.model) | map({model: .[0].model, inputTokens: (map(.input) | add), outputTokens: (map(.output) | add)})' "$TRANSCRIPT_FILE")
CACHE_READ_TOKENS=$(jq -s '[.[] | select(.type == "assistant") | ((.message.usage // .usage).cache_read_input_tokens // 0)] | add // 0' "$TRANSCRIPT_FILE")
CACHE_WRITE_TOKENS=$(jq -s '[.[] | select(.type == "assistant") | ((.message.usage // .usage).cache_creation_input_tokens // 0)] | add // 0' "$TRANSCRIPT_FILE")
TOTAL_TOKENS=$((INPUT_TOKENS + OUTPUT_TOKENS + CACHE_READ_TOKENS + CACHE_WRITE_TOKENS))

FIRST_TS=$(jq -s '[.[] | .timestamp // empty] | first // null' "$TRANSCRIPT_FILE")
LAST_TS=$(jq -s '[.[] | .timestamp // empty] | last // null' "$TRANSCRIPT_FILE")

# Sum total_tokens from subagent <usage> tags embedded in tool_result content
SUBAGENT_TOTAL_TOKENS=$({ grep -o 'total_tokens: [0-9]*' "$TRANSCRIPT_FILE" 2>/dev/null || true; } | awk -F': ' '{sum += $2} END {print sum+0}')

# Per-model subagent token breakdown via tool_use_id correlation
SUBAGENT_TOKENS_BY_MODEL=$(python3 - "$TRANSCRIPT_FILE" <<'PYEOF'
import json, re, sys
from collections import defaultdict

with open(sys.argv[1]) as f:
    lines = f.readlines()

# Map tool_use_id -> model (short name or subagent_type fallback)
tool_model = {}
for line in lines:
    try:
        obj = json.loads(line)
        content = obj.get('message', {}).get('content', obj.get('content', []))
        if not isinstance(content, list): continue
        for block in content:
            if isinstance(block, dict) and block.get('type') == 'tool_use' and block.get('name') == 'Agent':
                tid = block.get('id')
                inp = block.get('input', {})
                model = inp.get('model') or inp.get('subagent_type') or 'unknown'
                if tid:
                    tool_model[tid] = model
    except Exception:
        pass

model_tokens = defaultdict(int)
for line in lines:
    try:
        obj = json.loads(line)
        content = obj.get('message', {}).get('content', obj.get('content', []))
        if not isinstance(content, list): continue
        for block in content:
            if isinstance(block, dict) and block.get('type') == 'tool_result':
                tid = block.get('tool_use_id', '')
                model = tool_model.get(tid, 'unknown')
                inner = block.get('content', '')
                if isinstance(inner, list):
                    inner = ' '.join(b.get('text', '') for b in inner if isinstance(b, dict))
                m = re.search(r'total_tokens: (\d+)', str(inner))
                if m:
                    model_tokens[model] += int(m.group(1))
    except Exception:
        pass

result = [{'model': k, 'totalTokens': v} for k, v in sorted(model_tokens.items())]
print(json.dumps(result))
PYEOF
)

# Find a base to diff against: prefer HEAD~1, fall back to empty tree (first commit)
DIFF_BASE=""
if git rev-parse HEAD~1 >/dev/null 2>&1; then
  DIFF_BASE="HEAD~1"
elif git rev-parse HEAD >/dev/null 2>&1; then
  DIFF_BASE=$(git hash-object -t tree /dev/null)
fi

DIFF_STAT=""
if [[ -n "$DIFF_BASE" ]]; then
  DIFF_STAT=$(git diff --stat "$DIFF_BASE" 2>/dev/null || echo "")
fi
FILES_CHANGED=$(echo "$DIFF_STAT" | grep -c ' | ' || true)
INSERTIONS=$(echo "$DIFF_STAT" | tail -1 | grep -oE '[0-9]+ insertion' | grep -oE '[0-9]+' || true)
INSERTIONS=${INSERTIONS:-0}
DELETIONS=$(echo "$DIFF_STAT" | tail -1 | grep -oE '[0-9]+ deletion' | grep -oE '[0-9]+' || true)
DELETIONS=${DELETIONS:-0}

CHANGED_FILES=$([[ -n "$DIFF_BASE" ]] && git diff --name-only "$DIFF_BASE" 2>/dev/null | jq -R -s 'split("\n") | map(select(. != ""))' || echo '[]')

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
  --argjson cache_read_tokens  "$CACHE_READ_TOKENS" \
  --argjson cache_write_tokens "$CACHE_WRITE_TOKENS" \
  --argjson subagent_total_tokens "$SUBAGENT_TOTAL_TOKENS" \
  --argjson token_by_model "$TOKEN_BY_MODEL" \
  --argjson subagent_tokens_by_model "$SUBAGENT_TOKENS_BY_MODEL" \
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
    changedFilesList: $changed_files,
    cacheReadTokens:  $cache_read_tokens,
    cacheWriteTokens: $cache_write_tokens,
    subagentTotalTokens: $subagent_total_tokens,
    tokensByModel: $token_by_model,
    subagentTokensByModel: $subagent_tokens_by_model
  }' > "$OUTPUT_DIR/metrics.json"

echo "Metrics written to $OUTPUT_DIR/metrics.json"
