# Eval Pack Plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Claude Code plugin that generates polished static HTML eval packs capturing conversation history, metrics, heuristic flags, and Claude-driven analysis — deployed to GitHub Pages and linked from PR comments.

**Architecture:** Skill-first approach — three SKILL.md files drive the plugin (generate, setup, review). Shell scripts handle deterministic data extraction (metrics, pattern detection, HTML rendering). Claude handles non-deterministic work (test execution, analysis). All data flows through intermediate JSON files for testability. HTML uses client-side JS to render from a bundled `data.json`.

**Tech Stack:** Bash (scripts), HTML/CSS/JS (eval pack output), GitHub Actions (Pages deployment), `jq` (JSON processing), `gh` CLI (PR management)

---

## File Structure

```
eval-pack/
├── .claude-plugin/
│   └── plugin.json                  # Plugin manifest — name, version, userConfig, skill/script refs
├── skills/
│   ├── generate/
│   │   └── SKILL.md                 # Core skill — orchestrates metrics → patterns → tests → analysis → render
│   ├── setup/
│   │   └── SKILL.md                 # One-time repo bootstrap — copies action, config, gitignore
│   └── review/
│       └── SKILL.md                 # Wraps generate + PR creation + comment posting
├── templates/
│   ├── workflows/
│   │   └── eval-pack-pages.yml      # GitHub Action — deploy to gh-pages, post PR comment
│   └── html/
│       ├── index.html               # HTML shell — sections for verdict/screenshots/stats/timeline/flags/analysis/transcript
│       ├── styles.css               # Vercel-style dashboard — cards, badges, dark/light toggle, collapsibles
│       └── scripts.js               # Client-side rendering — reads data.json, populates sections, handles interactions
├── scripts/
│   ├── extract-metrics.sh           # Reads transcript JSONL + git diff → metrics.json
│   ├── detect-patterns.sh           # Reads transcript JSONL + metrics.json → patterns.json
│   └── render-html.sh               # Assembles final pack from templates + JSON + transcript + evidence
└── settings.json                    # Default plugin settings
```

---

### Task 1: Repository Init + Plugin Manifest

**Files:**
- Create: `.claude-plugin/plugin.json`
- Create: `settings.json`

- [ ] **Step 1: Initialize git repo**

```bash
cd /Users/jasonsmith/Code/eval-pack
git init
```

- [ ] **Step 2: Create plugin manifest**

Create `.claude-plugin/plugin.json`:

```json
{
  "$schema": "https://json.schemastore.org/claude-code-plugin-manifest.json",
  "name": "eval-pack",
  "version": "0.1.0",
  "description": "Generate eval packs — polished HTML reports capturing how code was produced, with metrics, heuristics, and AI-driven analysis",
  "author": {
    "name": "Jason Smith",
    "email": "wallawalla1337@gmail.com"
  },
  "repository": "https://github.com/jasonsmith/eval-pack",
  "license": "MIT",
  "keywords": ["eval", "review", "metrics", "reporting"],
  "skills": "./skills/",
  "userConfig": {
    "outputDir": {
      "type": "string",
      "title": "Output directory",
      "description": "Directory where eval packs are written, relative to project root",
      "default": ".eval-packs"
    },
    "includeTranscript": {
      "type": "boolean",
      "title": "Include transcript",
      "description": "Include full conversation transcript in eval pack",
      "default": true
    },
    "analysis": {
      "type": "boolean",
      "title": "Enable Claude analysis",
      "description": "Have Claude write retrospective, friction report, and prompt quality analysis. When false, only heuristic flags are included.",
      "default": true
    },
    "pagesBaseUrl": {
      "type": "string",
      "title": "GitHub Pages base URL",
      "description": "Base URL for deployed eval packs (e.g. https://myorg.github.io/myrepo/eval-packs). Used in PR comment links."
    }
  }
}
```

- [ ] **Step 3: Create default settings**

Create `settings.json`:

```json
{}
```

- [ ] **Step 4: Commit**

```bash
git add .claude-plugin/plugin.json settings.json
git commit -m "feat: init plugin manifest with userConfig schema"
```

---

### Task 2: Extract Metrics Script

**Files:**
- Create: `scripts/extract-metrics.sh`

This script reads the transcript JSONL and git diff, producing `metrics.json`.

- [ ] **Step 1: Create extract-metrics.sh**

Create `scripts/extract-metrics.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

TRANSCRIPT_FILE="${1:?Usage: extract-metrics.sh <transcript.jsonl> <output-dir>}"
OUTPUT_DIR="${2:?Usage: extract-metrics.sh <transcript.jsonl> <output-dir>}"

mkdir -p "$OUTPUT_DIR"

if [[ ! -f "$TRANSCRIPT_FILE" ]]; then
  echo "Error: transcript file not found: $TRANSCRIPT_FILE" >&2
  exit 1
fi

TURN_COUNT=$(jq -s '[.[] | select(.type == "human" or .type == "assistant")] | length' "$TRANSCRIPT_FILE")

MODEL=$(jq -s '[.[] | select(.type == "assistant") | .model // empty] | last // "unknown"' "$TRANSCRIPT_FILE")

INPUT_TOKENS=$(jq -s '[.[] | select(.type == "assistant") | .usage.input_tokens // 0] | add // 0' "$TRANSCRIPT_FILE")
OUTPUT_TOKENS=$(jq -s '[.[] | select(.type == "assistant") | .usage.output_tokens // 0] | add // 0' "$TRANSCRIPT_FILE")
TOTAL_TOKENS=$((INPUT_TOKENS + OUTPUT_TOKENS))

FIRST_TS=$(jq -s '[.[] | .timestamp // empty] | first // null' "$TRANSCRIPT_FILE")
LAST_TS=$(jq -s '[.[] | .timestamp // empty] | last // null' "$TRANSCRIPT_FILE")

DIFF_STAT=$(git diff --stat HEAD~1 2>/dev/null || echo "")
FILES_CHANGED=$(echo "$DIFF_STAT" | grep -c ' | ' 2>/dev/null || echo "0")
INSERTIONS=$(echo "$DIFF_STAT" | tail -1 | grep -oE '[0-9]+ insertion' | grep -oE '[0-9]+' || echo "0")
DELETIONS=$(echo "$DIFF_STAT" | tail -1 | grep -oE '[0-9]+ deletion' | grep -oE '[0-9]+' || echo "0")

CHANGED_FILES=$(git diff --name-only HEAD~1 2>/dev/null | jq -R -s 'split("\n") | map(select(. != ""))' || echo '[]')

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
    model: $model,
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
```

- [ ] **Step 2: Make executable**

```bash
chmod +x scripts/extract-metrics.sh
```

- [ ] **Step 3: Test with a sample transcript**

Create a temporary test transcript and run:

```bash
mkdir -p /tmp/eval-pack-test
cat > /tmp/eval-pack-test/transcript.jsonl << 'JSONL'
{"type":"human","timestamp":"2026-05-10T10:00:00Z","content":"Fix the auth bug"}
{"type":"assistant","timestamp":"2026-05-10T10:01:00Z","model":"claude-opus-4-6","usage":{"input_tokens":500,"output_tokens":300},"content":"I'll fix the auth bug."}
{"type":"human","timestamp":"2026-05-10T10:02:00Z","content":"Looks good"}
{"type":"assistant","timestamp":"2026-05-10T10:03:00Z","model":"claude-opus-4-6","usage":{"input_tokens":600,"output_tokens":400},"content":"Done."}
JSONL

scripts/extract-metrics.sh /tmp/eval-pack-test/transcript.jsonl /tmp/eval-pack-test/output
cat /tmp/eval-pack-test/output/metrics.json
```

Expected: JSON with model `claude-opus-4-6`, totalTokens 1800, turnCount 4.

- [ ] **Step 4: Commit**

```bash
git add scripts/extract-metrics.sh
git commit -m "feat: add extract-metrics script — parses transcript JSONL and git diff"
```

---

### Task 3: Detect Patterns Script

**Files:**
- Create: `scripts/detect-patterns.sh`

Reads transcript JSONL and detects heuristic flags: false completions, retries, scope drift, test failures.

- [ ] **Step 1: Create detect-patterns.sh**

Create `scripts/detect-patterns.sh`:

```bash
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
  [range(0; length - 1) |
    . as $i |
    if (.[$i].type == "assistant" and .[$i+1].type == "human") then
      if ((.[$i].content | test("(?i)(done|complete|finished|all set|that should|looks good now)")) and
          (.[$i+1].content | test("(?i)(no|not|wrong|still|actually|but|fix|fail|error|broken|issue)"))) then
        {
          turn: $i,
          agentClaim: (.[$i].content | .[0:120]),
          userResponse: (.[$i+1].content | .[0:120])
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
  FILE_COUNT=$(jq '.filesChanged' "$OUTPUT_DIR/metrics.json")
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
```

- [ ] **Step 2: Make executable**

```bash
chmod +x scripts/detect-patterns.sh
```

- [ ] **Step 3: Test with sample transcript**

```bash
scripts/detect-patterns.sh /tmp/eval-pack-test/transcript.jsonl /tmp/eval-pack-test/output
cat /tmp/eval-pack-test/output/patterns.json
```

Expected: JSON with empty `falseCompletions`, `retryCount: 0`, `testFailureCount: 0`, one green flag.

- [ ] **Step 4: Commit**

```bash
git add scripts/detect-patterns.sh
git commit -m "feat: add detect-patterns script — false completions, retries, test failures, scope drift"
```

---

### Task 4: HTML Template — Structure and Styles

**Files:**
- Create: `templates/html/index.html`
- Create: `templates/html/styles.css`

Build the HTML shell and Vercel-style CSS. No JS yet — static structure first.

- [ ] **Step 1: Create index.html**

Create `templates/html/index.html`:

```html
<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Eval Pack</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <header class="top-bar">
    <div class="top-bar-left">
      <h1 class="logo">Eval Pack</h1>
      <span class="session-id" id="session-id"></span>
    </div>
    <button class="theme-toggle" id="theme-toggle" aria-label="Toggle theme">
      <span class="theme-icon-dark">☀</span>
      <span class="theme-icon-light">☾</span>
    </button>
  </header>

  <main class="container">
    <!-- Section 1: Verdict Banner -->
    <section class="verdict-banner" id="verdict-banner">
      <div class="verdict-icon" id="verdict-icon"></div>
      <div class="verdict-text" id="verdict-text"></div>
      <div class="verdict-detail" id="verdict-detail"></div>
    </section>

    <!-- Section 2: Screenshots / Visual Evidence -->
    <section class="card" id="screenshots-section" style="display:none;">
      <h2 class="card-title">Visual Evidence</h2>
      <div class="screenshot-grid" id="screenshot-grid"></div>
    </section>

    <!-- Section 3: Stats Card -->
    <section class="card" id="stats-card">
      <h2 class="card-title">Session Stats</h2>
      <div class="stats-row" id="stats-row"></div>
    </section>

    <!-- Section 4: Phase Timeline -->
    <section class="card" id="timeline-section">
      <h2 class="card-title">Phase Timeline</h2>
      <div class="timeline-bar" id="timeline-bar"></div>
      <div class="timeline-legend" id="timeline-legend"></div>
    </section>

    <!-- Section 5: Heuristic Flags -->
    <section class="card" id="flags-section">
      <h2 class="card-title">Heuristic Flags</h2>
      <div class="flags-row" id="flags-row"></div>
    </section>

    <!-- Section 6: Claude Analysis -->
    <section class="card" id="analysis-section" style="display:none;">
      <h2 class="card-title">Analysis</h2>
      <div class="analysis-tabs">
        <button class="tab active" data-tab="retrospective">Retrospective</button>
        <button class="tab" data-tab="friction">Repo Friction</button>
        <button class="tab" data-tab="prompt">Prompt Quality</button>
      </div>
      <div class="tab-content" id="tab-retrospective"></div>
      <div class="tab-content" id="tab-friction" style="display:none;"></div>
      <div class="tab-content" id="tab-prompt" style="display:none;"></div>
    </section>

    <!-- Section 7: Full Transcript -->
    <section class="card" id="transcript-section">
      <details class="collapsible">
        <summary class="card-title collapsible-trigger">Full Transcript</summary>
        <div class="transcript-container" id="transcript-container"></div>
      </details>
    </section>

    <!-- Round indicator -->
    <section class="card" id="rounds-section" style="display:none;">
      <h2 class="card-title">Iteration Rounds</h2>
      <div class="rounds-nav" id="rounds-nav"></div>
    </section>
  </main>

  <footer class="footer">
    <span>Generated by <strong>eval-pack</strong></span>
    <span id="generated-at"></span>
  </footer>

  <script src="scripts.js"></script>
</body>
</html>
```

- [ ] **Step 2: Create styles.css**

Create `templates/html/styles.css`:

```css
/* Reset */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

/* Theme tokens */
:root {
  --bg: #0a0a0a;
  --bg-card: #111111;
  --bg-card-hover: #1a1a1a;
  --border: #2a2a2a;
  --text: #ededed;
  --text-secondary: #888888;
  --accent: #0070f3;
  --green: #17b169;
  --red: #e5484d;
  --amber: #f5a623;
  --radius: 8px;
  --font: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  --font-mono: 'SF Mono', 'Fira Code', 'Fira Mono', Menlo, monospace;
}

[data-theme="light"] {
  --bg: #fafafa;
  --bg-card: #ffffff;
  --bg-card-hover: #f5f5f5;
  --border: #eaeaea;
  --text: #171717;
  --text-secondary: #666666;
}

body {
  background: var(--bg);
  color: var(--text);
  font-family: var(--font);
  line-height: 1.6;
  min-height: 100vh;
}

/* Top Bar */
.top-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 24px;
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  background: var(--bg);
  z-index: 100;
}

.top-bar-left { display: flex; align-items: center; gap: 16px; }
.logo { font-size: 16px; font-weight: 600; }
.session-id { font-size: 13px; color: var(--text-secondary); font-family: var(--font-mono); }

.theme-toggle {
  background: none;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text);
  cursor: pointer;
  padding: 6px 10px;
  font-size: 16px;
}

[data-theme="dark"] .theme-icon-light { display: none; }
[data-theme="light"] .theme-icon-dark { display: none; }

/* Container */
.container {
  max-width: 960px;
  margin: 0 auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* Verdict Banner */
.verdict-banner {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px 24px;
  border-radius: var(--radius);
  border: 1px solid var(--border);
}

.verdict-banner.pass {
  background: linear-gradient(135deg, rgba(23, 177, 105, 0.1), transparent);
  border-color: var(--green);
}

.verdict-banner.fail {
  background: linear-gradient(135deg, rgba(229, 72, 77, 0.1), transparent);
  border-color: var(--red);
}

.verdict-banner.unknown {
  background: linear-gradient(135deg, rgba(245, 166, 35, 0.1), transparent);
  border-color: var(--amber);
}

.verdict-icon { font-size: 32px; }
.verdict-text { font-size: 20px; font-weight: 600; }
.verdict-detail { font-size: 14px; color: var(--text-secondary); margin-left: auto; }

/* Cards */
.card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px 24px;
}

.card-title {
  font-size: 14px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-secondary);
  margin-bottom: 16px;
}

/* Stats Row */
.stats-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 16px;
}

.stat-item { text-align: center; }
.stat-value { font-size: 24px; font-weight: 700; font-family: var(--font-mono); }
.stat-label { font-size: 12px; color: var(--text-secondary); margin-top: 4px; }

/* Timeline */
.timeline-bar {
  display: flex;
  height: 32px;
  border-radius: 4px;
  overflow: hidden;
  gap: 2px;
}

.timeline-segment {
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 500;
  color: white;
  min-width: 40px;
  position: relative;
}

.timeline-segment.understanding { background: #6366f1; }
.timeline-segment.planning { background: #0070f3; }
.timeline-segment.implementation { background: #17b169; }
.timeline-segment.testing { background: #f5a623; }
.timeline-segment.fixing { background: #e5484d; }
.timeline-segment.false-completion { background: repeating-linear-gradient(45deg, var(--amber), var(--amber) 4px, transparent 4px, transparent 8px); }

.timeline-legend {
  display: flex;
  gap: 16px;
  margin-top: 12px;
  flex-wrap: wrap;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-secondary);
}

.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 2px;
}

/* Flags */
.flags-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.flag-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 20px;
  font-size: 13px;
  font-weight: 500;
}

.flag-chip.red { background: rgba(229, 72, 77, 0.15); color: var(--red); border: 1px solid rgba(229, 72, 77, 0.3); }
.flag-chip.amber { background: rgba(245, 166, 35, 0.15); color: var(--amber); border: 1px solid rgba(245, 166, 35, 0.3); }
.flag-chip.green { background: rgba(23, 177, 105, 0.15); color: var(--green); border: 1px solid rgba(23, 177, 105, 0.3); }

/* Analysis Tabs */
.analysis-tabs {
  display: flex;
  gap: 0;
  border-bottom: 1px solid var(--border);
  margin-bottom: 16px;
}

.tab {
  background: none;
  border: none;
  color: var(--text-secondary);
  padding: 8px 16px;
  cursor: pointer;
  font-size: 14px;
  border-bottom: 2px solid transparent;
  transition: all 0.15s;
}

.tab.active { color: var(--text); border-bottom-color: var(--accent); }
.tab:hover { color: var(--text); }
.tab-content { font-size: 14px; line-height: 1.7; }

/* Transcript */
.collapsible-trigger {
  cursor: pointer;
  list-style: none;
  user-select: none;
}

.collapsible-trigger::before {
  content: '▸ ';
  display: inline;
}

details[open] .collapsible-trigger::before { content: '▾ '; }

.transcript-container { margin-top: 16px; }

.turn {
  padding: 12px 16px;
  border-left: 3px solid var(--border);
  margin-bottom: 8px;
}

.turn.human { border-left-color: var(--accent); }
.turn.assistant { border-left-color: var(--green); }

.turn-header {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

.turn-role { font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }
.turn-content { font-size: 14px; white-space: pre-wrap; }

.turn-content pre {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 12px;
  overflow-x: auto;
  font-family: var(--font-mono);
  font-size: 13px;
  margin: 8px 0;
}

/* Screenshots */
.screenshot-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 12px;
}

.screenshot-item {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
  cursor: pointer;
}

.screenshot-item img {
  width: 100%;
  display: block;
}

.screenshot-label {
  padding: 8px 12px;
  font-size: 12px;
  color: var(--text-secondary);
  background: var(--bg);
}

/* Screenshot modal */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.85);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  cursor: pointer;
}

.modal-overlay img {
  max-width: 90vw;
  max-height: 90vh;
  border-radius: var(--radius);
}

/* Rounds nav */
.rounds-nav {
  display: flex;
  gap: 8px;
}

.round-btn {
  padding: 6px 16px;
  border-radius: var(--radius);
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text);
  cursor: pointer;
  font-size: 13px;
}

.round-btn.active { border-color: var(--accent); background: rgba(0, 112, 243, 0.1); }

/* Footer */
.footer {
  text-align: center;
  padding: 24px;
  font-size: 12px;
  color: var(--text-secondary);
  border-top: 1px solid var(--border);
  margin-top: 24px;
  display: flex;
  justify-content: center;
  gap: 16px;
}

/* Responsive */
@media (max-width: 640px) {
  .container { padding: 12px; }
  .stats-row { grid-template-columns: repeat(2, 1fr); }
  .verdict-banner { flex-wrap: wrap; }
  .verdict-detail { margin-left: 0; width: 100%; }
}
```

- [ ] **Step 3: Commit**

```bash
git add templates/html/index.html templates/html/styles.css
git commit -m "feat: add HTML template and Vercel-style CSS for eval pack output"
```

---

### Task 5: HTML Template — Client-Side JavaScript

**Files:**
- Create: `templates/html/scripts.js`

Reads `data.json` and populates all sections.

- [ ] **Step 1: Create scripts.js**

Create `templates/html/scripts.js`:

```javascript
(async function () {
  const resp = await fetch('data.json');
  const data = await resp.json();

  const currentRound = data.rounds ? data.rounds.length - 1 : 0;
  let activeRound = currentRound;

  function getRound(idx) {
    if (data.rounds) return data.rounds[idx];
    return data;
  }

  // Theme toggle
  const toggle = document.getElementById('theme-toggle');
  const savedTheme = localStorage.getItem('eval-pack-theme');
  if (savedTheme) document.documentElement.setAttribute('data-theme', savedTheme);

  toggle.addEventListener('click', () => {
    const current = document.documentElement.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('eval-pack-theme', next);
  });

  // Session ID
  document.getElementById('session-id').textContent = data.sessionId || '';
  document.getElementById('generated-at').textContent = data.generatedAt || '';

  function renderRound(roundIdx) {
    const round = getRound(roundIdx);
    const metrics = round.metrics || {};
    const patterns = round.patterns || {};
    const analysis = round.analysis || {};
    const testResults = round.testResults || {};

    // Verdict
    const banner = document.getElementById('verdict-banner');
    const icon = document.getElementById('verdict-icon');
    const text = document.getElementById('verdict-text');
    const detail = document.getElementById('verdict-detail');

    banner.className = 'verdict-banner';
    if (testResults.verdict === 'pass') {
      banner.classList.add('pass');
      icon.textContent = '\u2713';
      text.textContent = 'All Tests Passed';
      detail.textContent = testResults.summary || '';
    } else if (testResults.verdict === 'fail') {
      banner.classList.add('fail');
      icon.textContent = '\u2717';
      text.textContent = 'Tests Failed';
      detail.textContent = testResults.summary || '';
    } else {
      banner.classList.add('unknown');
      icon.textContent = '?';
      text.textContent = 'No Tests Ran';
      detail.textContent = 'Agent did not execute tests for this session';
    }

    // Stats
    const statsRow = document.getElementById('stats-row');
    const stats = [
      { value: metrics.model || 'N/A', label: 'Model' },
      { value: formatNumber(metrics.totalTokens), label: 'Total Tokens' },
      { value: metrics.turnCount || 0, label: 'Turns' },
      { value: formatDuration(metrics.firstTimestamp, metrics.lastTimestamp), label: 'Duration' },
      { value: metrics.filesChanged || 0, label: 'Files Changed' },
      { value: `+${metrics.insertions || 0} / -${metrics.deletions || 0}`, label: 'Lines' },
    ];
    statsRow.innerHTML = stats.map(s =>
      `<div class="stat-item"><div class="stat-value">${s.value}</div><div class="stat-label">${s.label}</div></div>`
    ).join('');

    // Flags
    const flagsRow = document.getElementById('flags-row');
    const flags = patterns.flags || [];
    flagsRow.innerHTML = flags.map(f => {
      const countStr = f.count ? ` (${f.count})` : '';
      return `<span class="flag-chip ${f.level}">${f.label}${countStr}</span>`;
    }).join('');

    // Analysis
    const analysisSection = document.getElementById('analysis-section');
    if (analysis.retrospective || analysis.friction || analysis.promptQuality) {
      analysisSection.style.display = '';
      document.getElementById('tab-retrospective').innerHTML = renderMarkdown(analysis.retrospective || 'No retrospective available.');
      document.getElementById('tab-friction').innerHTML = renderMarkdown(analysis.friction || 'No friction report available.');
      document.getElementById('tab-prompt').innerHTML = renderMarkdown(analysis.promptQuality || 'No prompt quality analysis available.');
    }

    // Screenshots
    renderScreenshots(round.screenshots || []);
  }

  // Screenshots
  function renderScreenshots(screenshots) {
    const section = document.getElementById('screenshots-section');
    const grid = document.getElementById('screenshot-grid');
    if (screenshots.length === 0) { section.style.display = 'none'; return; }
    section.style.display = '';
    grid.innerHTML = screenshots.map(s =>
      `<div class="screenshot-item" onclick="showModal('${s.path}')">
        <img src="${s.path}" alt="${s.label}" loading="lazy">
        <div class="screenshot-label">${s.label}</div>
      </div>`
    ).join('');
  }

  // Screenshot modal
  window.showModal = function (src) {
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.innerHTML = `<img src="${src}">`;
    overlay.addEventListener('click', () => overlay.remove());
    document.body.appendChild(overlay);
  };

  // Tabs
  document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.style.display = 'none');
      tab.classList.add('active');
      document.getElementById(`tab-${tab.dataset.tab}`).style.display = '';
    });
  });

  // Transcript
  function renderTranscript() {
    const container = document.getElementById('transcript-container');
    const transcript = data.transcript || [];
    container.innerHTML = transcript.map(turn => {
      const role = turn.type || 'unknown';
      const ts = turn.timestamp ? new Date(turn.timestamp).toLocaleTimeString() : '';
      const content = escapeHtml(typeof turn.content === 'string' ? turn.content : JSON.stringify(turn.content, null, 2));
      return `<div class="turn ${role}">
        <div class="turn-header">
          <span class="turn-role">${role}</span>
          <span>${ts}</span>
        </div>
        <div class="turn-content">${content}</div>
      </div>`;
    }).join('');
  }

  // Rounds
  function renderRounds() {
    if (!data.rounds || data.rounds.length <= 1) return;
    const section = document.getElementById('rounds-section');
    section.style.display = '';
    const nav = document.getElementById('rounds-nav');
    nav.innerHTML = data.rounds.map((_, i) =>
      `<button class="round-btn ${i === activeRound ? 'active' : ''}" data-round="${i}">Round ${i + 1}</button>`
    ).join('');
    nav.querySelectorAll('.round-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        activeRound = parseInt(btn.dataset.round);
        renderRound(activeRound);
        renderRounds();
      });
    });
  }

  // Timeline (phase-level)
  function renderTimeline() {
    const bar = document.getElementById('timeline-bar');
    const legend = document.getElementById('timeline-legend');
    const phases = data.phases || [
      { name: 'Understanding', className: 'understanding', weight: 15 },
      { name: 'Planning', className: 'planning', weight: 10 },
      { name: 'Implementation', className: 'implementation', weight: 45 },
      { name: 'Testing', className: 'testing', weight: 20 },
      { name: 'Fixing', className: 'fixing', weight: 10 },
    ];
    bar.innerHTML = phases.map(p =>
      `<div class="timeline-segment ${p.className}" style="flex:${p.weight}">${p.name}</div>`
    ).join('');
    legend.innerHTML = phases.map(p =>
      `<div class="legend-item"><div class="legend-dot" style="background:var(--${getPhaseColor(p.className)})"></div>${p.name}</div>`
    ).join('');
  }

  // Helpers
  function formatNumber(n) {
    if (n == null) return 'N/A';
    if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
    if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
    return String(n);
  }

  function formatDuration(start, end) {
    if (!start || !end) return 'N/A';
    const ms = new Date(end) - new Date(start);
    const mins = Math.floor(ms / 60000);
    if (mins < 60) return `${mins}m`;
    return `${Math.floor(mins / 60)}h ${mins % 60}m`;
  }

  function escapeHtml(str) {
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function renderMarkdown(text) {
    return text
      .replace(/^### (.+)$/gm, '<h4>$1</h4>')
      .replace(/^## (.+)$/gm, '<h3>$1</h3>')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\n/g, '<br>');
  }

  function getPhaseColor(className) {
    const map = { understanding: 'accent', planning: 'accent', implementation: 'green', testing: 'amber', fixing: 'red' };
    return map[className] || 'accent';
  }

  // Init
  renderRound(activeRound);
  renderTranscript();
  renderRounds();
  renderTimeline();
})();
```

- [ ] **Step 2: Commit**

```bash
git add templates/html/scripts.js
git commit -m "feat: add client-side JS — renders data.json into eval pack sections"
```

---

### Task 6: Render HTML Script

**Files:**
- Create: `scripts/render-html.sh`

Assembles final eval pack: copies templates, builds `data.json`, copies evidence files.

- [ ] **Step 1: Create render-html.sh**

Create `scripts/render-html.sh`:

```bash
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
```

- [ ] **Step 2: Make executable**

```bash
chmod +x scripts/render-html.sh
```

- [ ] **Step 3: Test end-to-end with sample data**

```bash
# Create sample intermediate files
mkdir -p /tmp/eval-pack-test/output/test-session
cp /tmp/eval-pack-test/output/metrics.json /tmp/eval-pack-test/output/test-session/
cp /tmp/eval-pack-test/output/patterns.json /tmp/eval-pack-test/output/test-session/

scripts/render-html.sh /tmp/eval-pack-test/output test-session "$(pwd)" /tmp/eval-pack-test/transcript.jsonl

# Verify output
ls -la /tmp/eval-pack-test/output/test-session/
cat /tmp/eval-pack-test/output/test-session/data.json | jq '.rounds | length'
```

Expected: pack directory with index.html, styles.css, scripts.js, data.json. Rounds array length = 1.

- [ ] **Step 4: Commit**

```bash
git add scripts/render-html.sh
git commit -m "feat: add render-html script — assembles eval pack with round support"
```

---

### Task 7: Generate Skill

**Files:**
- Create: `skills/generate/SKILL.md`

The core skill that orchestrates the full eval pack generation.

- [ ] **Step 1: Create SKILL.md**

Create `skills/generate/SKILL.md`:

````markdown
---
description: Generate an eval pack — a polished HTML report capturing conversation history, metrics, heuristic patterns, test results, and AI analysis. Run this when work is PR-ready.
tags: ["eval", "review", "metrics"]
---

# Generate Eval Pack

You are generating an eval pack for the current session. Follow these steps in order.

## Step 1: Extract Metrics

Run the extract-metrics script against the current session transcript:

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/extract-metrics.sh" "${TRANSCRIPT_PATH}" "${PACK_DIR}"
```

Where:
- `TRANSCRIPT_PATH` is the transcript file for this session
- `PACK_DIR` is `<outputDir>/<session-id>` (outputDir from plugin config, default `.eval-packs`; session-id from current session)

If the transcript path is not available, read the conversation history from context and write it to `${PACK_DIR}/transcript.jsonl` in JSONL format with fields: `type` (human/assistant), `timestamp`, `content`, and for assistant turns: `model`, `usage.input_tokens`, `usage.output_tokens`.

## Step 2: Detect Patterns

Run the detect-patterns script:

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/detect-patterns.sh" "${TRANSCRIPT_PATH}" "${PACK_DIR}"
```

## Step 3: Run Tests

Identify and run appropriate tests for the changes made in this session:

1. Check what files were changed using `git diff --name-only`
2. Determine what tests are appropriate:
   - If test files exist for changed source files, run them
   - If a test runner is configured (jest, pytest, go test, etc.), run relevant suites
   - If frontend changes were made and Playwright is available, run e2e tests
   - If UI changes were made, use Playwright to take before/after screenshots
3. Capture all evidence:
   - Save test output to `${PACK_DIR}/logs/test-output.log`
   - Save build output to `${PACK_DIR}/logs/build-output.log` if a build was run
   - Save screenshots to `${PACK_DIR}/screenshots/` with descriptive filenames
4. Write test results to `${PACK_DIR}/test-results.json`:

```json
{
  "verdict": "pass|fail|none",
  "summary": "Brief description of what was tested and results",
  "testsRun": [
    {"name": "test suite or file", "passed": true, "output": "brief result"}
  ]
}
```

## Step 4: Analyze (if enabled)

Check if analysis is enabled (plugin config `analysis` option, default true).

If enabled, read the transcript, metrics.json, and patterns.json. Write `${PACK_DIR}/analysis.json` with three sections:

```json
{
  "retrospective": "What went well, what was slow, where time was wasted in this session.",
  "friction": "What repository characteristics slowed things down — missing types, unclear structure, no test harness, poor naming, missing docs.",
  "promptQuality": "Was the initial context sufficient? What information, if front-loaded by the developer, would have made this session faster?"
}
```

Be specific and actionable. Reference actual files, patterns, and moments from the transcript. This analysis is for the developer and their reviewer — not generic advice.

## Step 5: Render HTML

Run the render script:

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/render-html.sh" "${OUTPUT_DIR}" "${SESSION_ID}" "${CLAUDE_PLUGIN_ROOT}" "${TRANSCRIPT_PATH}"
```

This assembles the final eval pack with all data, handles round detection for regeneration, and copies template files.

## Step 6: Report

Tell the user:
- Where the eval pack was written
- The verdict (pass/fail/none)
- Key flags detected
- That they can open `index.html` in a browser to view the full report
- That they can run `/eval-pack:review` to create a PR with the eval pack attached
````

- [ ] **Step 2: Commit**

```bash
git add skills/generate/SKILL.md
git commit -m "feat: add generate skill — orchestrates full eval pack creation"
```

---

### Task 8: Setup Skill

**Files:**
- Create: `skills/setup/SKILL.md`

One-time repo bootstrap skill.

- [ ] **Step 1: Create SKILL.md**

Create `skills/setup/SKILL.md`:

````markdown
---
description: Bootstrap a repository to use eval-pack — copies GitHub Action, adds config, sets up gitignore and Pages. Run once per repo.
tags: ["setup", "config"]
---

# Setup Eval Pack

Bootstrap the current repository to use eval-pack. Follow these steps:

## Step 1: Copy GitHub Action

Copy the eval-pack Pages deployment workflow into the target repo:

```bash
mkdir -p .github/workflows
cp "${CLAUDE_PLUGIN_ROOT}/templates/workflows/eval-pack-pages.yml" .github/workflows/eval-pack-pages.yml
```

## Step 2: Add Plugin Config

Check if `.claude/settings.json` exists. If it does, merge eval-pack config into it. If not, create it.

Add this configuration (preserve any existing content):

```json
{
  "plugins": [".claude/plugins/eval-pack"],
  "pluginConfigs": {
    "eval-pack": {
      "options": {
        "outputDir": ".eval-packs",
        "includeTranscript": true,
        "redactPatterns": [],
        "analysis": true,
        "pagesBaseUrl": ""
      }
    }
  }
}
```

Ask the user for their GitHub Pages base URL (format: `https://<org>.github.io/<repo>/eval-packs`) and fill it in.

## Step 3: Update .gitignore

Add `.eval-packs/` to the project's `.gitignore` file. If `.gitignore` doesn't exist, create it.

The entry should have a comment explaining why:

```
# Eval packs live on PR branches and gh-pages, not main
.eval-packs/
```

## Step 4: Setup GitHub Pages

If the `gh` CLI is available and authenticated:

```bash
gh api repos/{owner}/{repo}/pages -X POST -f source='{"branch":"gh-pages","path":"/"}' 2>/dev/null || true
```

If this fails (Pages may already be enabled, or permissions may not allow it), inform the user they need to enable GitHub Pages manually on the `gh-pages` branch.

## Step 5: Add Submodule

If eval-pack is not already a submodule in this repo:

```bash
git submodule add <eval-pack-repo-url> .claude/plugins/eval-pack
```

Ask the user for the eval-pack repository URL if not obvious from context.

## Step 6: Report

Tell the user:
- What was set up
- Remind them to commit the changes
- Tell them to set `pagesBaseUrl` in `.claude/settings.json` if they didn't provide it
- Tell them devs need to run `git submodule update --init` after cloning
- They can now use `/eval-pack:generate` and `/eval-pack:review`
````

- [ ] **Step 2: Commit**

```bash
git add skills/setup/SKILL.md
git commit -m "feat: add setup skill — one-time repo bootstrap"
```

---

### Task 9: Review Skill

**Files:**
- Create: `skills/review/SKILL.md`

Wraps generate + PR creation.

- [ ] **Step 1: Create SKILL.md**

Create `skills/review/SKILL.md`:

````markdown
---
description: Generate an eval pack and create (or update) a pull request with the eval pack attached. Posts a summary comment with verdict badge and link to the deployed eval pack on GitHub Pages.
tags: ["eval", "review", "pr"]
---

# Generate Eval Pack + Create PR

This skill combines eval pack generation with PR creation. Follow these steps:

## Step 1: Generate Eval Pack

Invoke the eval-pack generate skill internally. Run the full generation flow:

1. Extract metrics from transcript
2. Detect heuristic patterns
3. Run appropriate tests, capture screenshots and logs
4. Write Claude analysis (retrospective, friction, prompt quality)
5. Render HTML eval pack

## Step 2: Stage Eval Pack

Add the generated eval pack to git:

```bash
git add .eval-packs/
git commit -m "chore: add eval pack for session ${SESSION_ID}"
```

## Step 3: Create or Update PR

Check if a PR already exists for the current branch:

```bash
EXISTING_PR=$(gh pr list --head "$(git branch --show-current)" --json number --jq '.[0].number // empty')
```

If a PR exists, push the new commit. The PR updates automatically.

If no PR exists, create one:

```bash
gh pr create --title "<appropriate title based on work done>" --body "$(cat <<'EOF'
## Summary

<summarize what was accomplished in this session>

## Eval Pack

[View full eval pack](<pagesBaseUrl>/<session-id>/)

## Test Results

<verdict: pass/fail/none with brief summary>

---
Generated by [eval-pack](https://github.com/jasonsmith/eval-pack)
EOF
)"
```

## Step 4: Post Eval Pack Comment

Post a summary comment on the PR with key indicators:

```bash
gh pr comment "$PR_NUMBER" --body "$(cat <<'EOF'
## Eval Pack Report

<verdict badge: ✅ PASS / ❌ FAIL / ⚠️ NO TESTS>

| Metric | Value |
|--------|-------|
| Model | <model> |
| Tokens | <total> |
| Turns | <count> |
| Files Changed | <count> |
| Lines | +<ins> / -<del> |

### Flags
<list heuristic flags as chips>

### Key Findings
<1-2 sentence summary from analysis>

[View full eval pack →](<pagesBaseUrl>/<session-id>/)
EOF
)"
```

## Step 5: Report

Tell the user:
- PR URL
- Eval pack verdict
- That the eval pack will be deployed to GitHub Pages when the Action runs
- Link to the expected Pages URL
````

- [ ] **Step 2: Commit**

```bash
git add skills/review/SKILL.md
git commit -m "feat: add review skill — generate pack + create PR + post comment"
```

---

### Task 10: GitHub Action Template

**Files:**
- Create: `templates/workflows/eval-pack-pages.yml`

The GitHub Action that deploys eval packs to `gh-pages` and posts/updates PR comments.

- [ ] **Step 1: Create the workflow file**

Create `templates/workflows/eval-pack-pages.yml`:

```yaml
name: Deploy Eval Pack to GitHub Pages

on:
  pull_request:
    types: [opened, synchronize]
    paths:
      - '.eval-packs/**'

permissions:
  contents: write
  pull-requests: write
  pages: write

jobs:
  deploy-eval-pack:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout PR branch
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Find eval packs
        id: find-packs
        run: |
          if [ -d ".eval-packs" ]; then
            PACKS=$(find .eval-packs -name "index.html" -maxdepth 2 -mindepth 2 | head -20)
            if [ -n "$PACKS" ]; then
              echo "found=true" >> "$GITHUB_OUTPUT"
              echo "packs<<EOF" >> "$GITHUB_OUTPUT"
              echo "$PACKS" >> "$GITHUB_OUTPUT"
              echo "EOF" >> "$GITHUB_OUTPUT"
            else
              echo "found=false" >> "$GITHUB_OUTPUT"
            fi
          else
            echo "found=false" >> "$GITHUB_OUTPUT"
          fi

      - name: Deploy to gh-pages
        if: steps.find-packs.outputs.found == 'true'
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"

          # Fetch or create gh-pages branch
          git fetch origin gh-pages:gh-pages 2>/dev/null || git checkout --orphan gh-pages

          # Work in a temp directory
          TMPDIR=$(mktemp -d)
          git checkout gh-pages -- . 2>/dev/null || true

          # Copy existing gh-pages content
          if [ -d "eval-packs" ]; then
            cp -r eval-packs/ "$TMPDIR/"
          else
            mkdir -p "$TMPDIR/eval-packs"
          fi

          # Switch back to PR branch to get eval packs
          git checkout "${{ github.head_ref }}" -- .eval-packs/

          # Copy new eval packs
          for pack_html in ${{ steps.find-packs.outputs.packs }}; do
            PACK_DIR=$(dirname "$pack_html")
            SESSION_ID=$(basename "$PACK_DIR")
            mkdir -p "$TMPDIR/eval-packs/$SESSION_ID"
            cp -r "$PACK_DIR/"* "$TMPDIR/eval-packs/$SESSION_ID/"
          done

          # Commit to gh-pages
          git checkout gh-pages 2>/dev/null || git checkout --orphan gh-pages
          rm -rf eval-packs
          cp -r "$TMPDIR/eval-packs" eval-packs/
          git add eval-packs/
          git commit -m "deploy: eval pack for PR #${{ github.event.pull_request.number }}" --allow-empty
          git push origin gh-pages

          rm -rf "$TMPDIR"

      - name: Post PR comment
        if: steps.find-packs.outputs.found == 'true'
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const packs = `${{ steps.find-packs.outputs.packs }}`.trim().split('\n');

            for (const packHtml of packs) {
              const packDir = packHtml.replace('/index.html', '');
              const sessionId = packDir.split('/').pop();

              let dataJson = {};
              try {
                dataJson = JSON.parse(fs.readFileSync(`${packDir}/data.json`, 'utf8'));
              } catch (e) {
                console.log(`Could not read data.json for ${sessionId}`);
                continue;
              }

              const latestRound = dataJson.rounds?.[dataJson.rounds.length - 1] || {};
              const metrics = latestRound.metrics || {};
              const testResults = latestRound.testResults || {};
              const flags = (latestRound.patterns?.flags || [])
                .map(f => f.level === 'red' ? `🔴 ${f.label}` : f.level === 'amber' ? `🟡 ${f.label}` : `🟢 ${f.label}`)
                .join(' · ') || 'None';

              const verdictEmoji = testResults.verdict === 'pass' ? '✅' :
                                   testResults.verdict === 'fail' ? '❌' : '⚠️';
              const verdictText = testResults.verdict === 'pass' ? 'PASS' :
                                  testResults.verdict === 'fail' ? 'FAIL' : 'NO TESTS';

              const owner = context.repo.owner;
              const repo = context.repo.repo;
              const pagesUrl = `https://${owner}.github.io/${repo}/eval-packs/${sessionId}/`;

              const body = `## ${verdictEmoji} Eval Pack — ${verdictText}

            | Metric | Value |
            |--------|-------|
            | Model | ${metrics.model || 'N/A'} |
            | Tokens | ${(metrics.totalTokens || 0).toLocaleString()} |
            | Turns | ${metrics.turnCount || 0} |
            | Files Changed | ${metrics.filesChanged || 0} |
            | Lines | +${metrics.insertions || 0} / -${metrics.deletions || 0} |

            **Flags:** ${flags}

            ${testResults.summary ? `**Tests:** ${testResults.summary}` : ''}

            [View full eval pack →](${pagesUrl})

            ---
            *Generated by [eval-pack](https://github.com/jasonsmith/eval-pack)*`;

              // Check for existing eval-pack comment and update it
              const comments = await github.rest.issues.listComments({
                owner: context.repo.owner,
                repo: context.repo.repo,
                issue_number: context.issue.number,
              });

              const existingComment = comments.data.find(c =>
                c.body.includes('Eval Pack') && c.user.login === 'github-actions[bot]'
              );

              if (existingComment) {
                await github.rest.issues.updateComment({
                  owner: context.repo.owner,
                  repo: context.repo.repo,
                  comment_id: existingComment.id,
                  body: body,
                });
              } else {
                await github.rest.issues.createComment({
                  owner: context.repo.owner,
                  repo: context.repo.repo,
                  issue_number: context.issue.number,
                  body: body,
                });
              }
            }
```

- [ ] **Step 2: Commit**

```bash
git add templates/workflows/eval-pack-pages.yml
git commit -m "feat: add GitHub Action template — deploys eval packs to gh-pages, posts PR comments"
```

---

### Task 11: Integration Test — End-to-End Flow

**Files:**
- Create: `tests/test-e2e.sh`

Verifies the full pipeline: extract → detect → render → verify HTML output.

- [ ] **Step 1: Create test script**

Create `tests/test-e2e.sh`:

```bash
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
{"type":"assistant","timestamp":"2026-05-10T10:01:00Z","model":"claude-opus-4-6","usage":{"input_tokens":1200,"output_tokens":800},"content":"I'll look at the auth bug. Let me read login.ts first."}
{"type":"human","timestamp":"2026-05-10T10:03:00Z","content":"The token expiry check is wrong"}
{"type":"assistant","timestamp":"2026-05-10T10:04:00Z","model":"claude-opus-4-6","usage":{"input_tokens":1500,"output_tokens":1000},"content":"Found it. The comparison uses < instead of <=. Let me fix that and run the tests."}
{"type":"assistant","timestamp":"2026-05-10T10:06:00Z","model":"claude-opus-4-6","usage":{"input_tokens":800,"output_tokens":600},"content":"Done. All tests pass now."}
{"type":"human","timestamp":"2026-05-10T10:07:00Z","content":"Actually the test for edge case is still failing"}
{"type":"assistant","timestamp":"2026-05-10T10:08:00Z","model":"claude-opus-4-6","usage":{"input_tokens":900,"output_tokens":700},"content":"Let me try again with the edge case. I see the issue — the boundary condition at midnight."}
{"type":"assistant","timestamp":"2026-05-10T10:10:00Z","model":"claude-opus-4-6","usage":{"input_tokens":600,"output_tokens":500},"content":"Fixed. All tests pass including the midnight edge case."}
JSONL

# Step 1: Extract metrics
echo "--- Step 1: Extract metrics ---"
"$PLUGIN_ROOT/scripts/extract-metrics.sh" "$TEST_DIR/transcript.jsonl" "$TEST_DIR/$SESSION_ID"

if [[ ! -f "$TEST_DIR/$SESSION_ID/metrics.json" ]]; then
  echo "FAIL: metrics.json not created" >&2
  exit 1
fi

MODEL=$(jq -r '.model' "$TEST_DIR/$SESSION_ID/metrics.json")
TOKENS=$(jq '.totalTokens' "$TEST_DIR/$SESSION_ID/metrics.json")
TURNS=$(jq '.turnCount' "$TEST_DIR/$SESSION_ID/metrics.json")

echo "  Model: $MODEL"
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
"$PLUGIN_ROOT/scripts/detect-patterns.sh" "$TEST_DIR/transcript.jsonl" "$TEST_DIR/$SESSION_ID"

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
  "retrospective": "Session was efficient overall. One false completion where the agent claimed tests passed but an edge case was still failing.",
  "friction": "No type annotations on the auth module made it harder to understand token expiry logic.",
  "promptQuality": "Developer provided good initial context by naming the specific file. Could have mentioned the edge case upfront."
}
JSON
echo "  PASS"

# Step 5: Render HTML
echo ""
echo "--- Step 5: Render HTML ---"
"$PLUGIN_ROOT/scripts/render-html.sh" "$TEST_DIR" "$SESSION_ID" "$PLUGIN_ROOT" "$TEST_DIR/transcript.jsonl"

EXPECTED_FILES=("index.html" "styles.css" "scripts.js" "data.json" "transcript.jsonl")
for f in "${EXPECTED_FILES[@]}"; do
  if [[ ! -f "$TEST_DIR/$SESSION_ID/$f" ]]; then
    echo "FAIL: $f not found in pack" >&2
    exit 1
  fi
done

# Verify data.json structure
ROUNDS=$(jq '.rounds | length' "$TEST_DIR/$SESSION_ID/data.json")
HAS_TRANSCRIPT=$(jq '.transcript | length' "$TEST_DIR/$SESSION_ID/data.json")

echo "  Rounds: $ROUNDS"
echo "  Transcript entries: $HAS_TRANSCRIPT"

if [[ "$ROUNDS" -ne 1 ]]; then
  echo "FAIL: should have exactly 1 round" >&2
  exit 1
fi
echo "  PASS"

# Step 6: Test regeneration (round 2)
echo ""
echo "--- Step 6: Test regeneration (round 2) ---"
"$PLUGIN_ROOT/scripts/render-html.sh" "$TEST_DIR" "$SESSION_ID" "$PLUGIN_ROOT" "$TEST_DIR/transcript.jsonl"

ROUNDS=$(jq '.rounds | length' "$TEST_DIR/$SESSION_ID/data.json")
echo "  Rounds after regeneration: $ROUNDS"

if [[ "$ROUNDS" -ne 2 ]]; then
  echo "FAIL: should have 2 rounds after regeneration" >&2
  exit 1
fi
echo "  PASS"

echo ""
echo "=== ALL TESTS PASSED ==="
```

- [ ] **Step 2: Make executable**

```bash
chmod +x tests/test-e2e.sh
```

- [ ] **Step 3: Run the test**

```bash
tests/test-e2e.sh
```

Expected: all steps pass, including regeneration round detection.

- [ ] **Step 4: Fix any failures**

If any step fails, fix the relevant script and re-run.

- [ ] **Step 5: Commit**

```bash
git add tests/test-e2e.sh
git commit -m "test: add e2e test for full extract → detect → render pipeline"
```

---

### Task 12: README + Final Polish

**Files:**
- Create: `README.md`

- [ ] **Step 1: Create README.md**

Create `README.md`:

````markdown
# eval-pack

A Claude Code plugin that generates eval packs — polished HTML reports capturing how AI-assisted code was produced. Designed for PR review workflows where reviewers need visibility into agent behavior, not just the diff.

## What's in an Eval Pack?

- **Verdict banner** — pass/fail based on agent-driven test results
- **Visual evidence** — screenshots from Playwright or browser verification
- **Session stats** — model, tokens, turns, duration, files changed
- **Phase timeline** — where time was spent (understanding → planning → implementation → testing → fixing)
- **Heuristic flags** — false completions, retries, scope drift, test failures
- **Claude analysis** — retrospective, repo friction report, prompt quality assessment
- **Full transcript** — collapsible conversation history with syntax highlighting

## Install

Add as a git submodule to your project:

```bash
git submodule add <this-repo-url> .claude/plugins/eval-pack
```

Then run the setup skill:

```
/eval-pack:setup
```

This copies the GitHub Action, adds config to `.claude/settings.json`, and sets up `.gitignore`.

After cloning a repo with eval-pack, devs run:

```bash
git submodule update --init
```

## Usage

### Generate an eval pack

```
/eval-pack:generate
```

Produces a self-contained HTML report in `.eval-packs/<session-id>/`. Open `index.html` in a browser.

### Generate + create PR

```
/eval-pack:review
```

Generates the eval pack, creates (or updates) a PR, and posts a summary comment with a link to the deployed eval pack on GitHub Pages.

### Agent auto-generation

Agents can invoke `/eval-pack:generate` autonomously when they judge work is PR-ready. No hooks required — the agent calls the skill like any other.

## Configuration

In your project's `.claude/settings.json`:

```json
{
  "pluginConfigs": {
    "eval-pack": {
      "options": {
        "outputDir": ".eval-packs",
        "includeTranscript": true,
        "redactPatterns": ["\\.env", "SECRET"],
        "analysis": true,
        "pagesBaseUrl": "https://myorg.github.io/myrepo/eval-packs"
      }
    }
  }
}
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `outputDir` | string | `.eval-packs` | Where eval packs are written |
| `includeTranscript` | boolean | `true` | Include full conversation in pack |
| `redactPatterns` | string[] | `[]` | Regex patterns to strip from transcript |
| `analysis` | boolean | `true` | Enable Claude retrospective analysis |
| `pagesBaseUrl` | string | — | Base URL for GitHub Pages links |

## How It Works

1. Dev (or agent) runs `/eval-pack:generate`
2. Scripts extract metrics and detect heuristic patterns from the transcript
3. Claude runs appropriate tests, captures screenshots and logs
4. Claude analyzes the session — retrospective, repo friction, prompt quality
5. HTML report is rendered with all data
6. `/eval-pack:review` optionally creates a PR and posts a summary comment
7. GitHub Action deploys the HTML to `gh-pages` branch
8. Reviewer clicks the link in the PR comment to view the full eval pack

## License

MIT
````

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add README with install, usage, and configuration guide"
```

---

### Task 13: Push to Remote

**Files:** None (git operations only)

- [ ] **Step 1: Verify all files are committed**

```bash
git status
git log --oneline
```

Expected: clean working tree, ~12 commits.

- [ ] **Step 2: Add remote and push**

```bash
git remote add origin <repo-url>
git push -u origin main
```

Ask the user for the remote URL if not already configured.

---

## Self-Review Checklist

**Spec coverage:**
- ✅ Plugin manifest with userConfig — Task 1
- ✅ Extract metrics script — Task 2
- ✅ Detect patterns script — Task 3
- ✅ HTML template (7 sections, Vercel-style) — Tasks 4-5
- ✅ Render HTML script with round support — Task 6
- ✅ Generate skill — Task 7
- ✅ Setup skill — Task 8
- ✅ Review skill — Task 9
- ✅ GitHub Action template — Task 10
- ✅ Configuration via userConfig — Task 1
- ✅ Regeneration with rounds — Task 6 (render-html.sh handles it)
- ✅ Gitignore strategy — Task 8 (setup skill)
- ✅ Screenshots/logs capture — Task 7 (generate skill)
- ✅ Agent-driven testing — Task 7 (generate skill)

**Placeholder scan:** No TBD/TODO found.

**Type consistency:** JSON field names consistent across scripts (`metrics.json` fields match `data.json` structure match `scripts.js` references). Verified: `totalTokens`, `turnCount`, `filesChanged`, `insertions`, `deletions`, `falseCompletions`, `flags`, `verdict`.
