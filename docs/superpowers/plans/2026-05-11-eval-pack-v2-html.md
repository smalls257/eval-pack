# Eval Pack v2 HTML Redesign

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the eval-pack plugin's HTML output from a simple dashboard into a structured, tab-navigated report aligned with the reference design. The new schema (`analysis.json`) replaces three flat text fields with rich structured data covering eight reporting dimensions.

**Architecture:** The generate skill writes a new structured `analysis.json`. The HTML shell, styles, and client-side JS are replaced in full. The render script and e2e test require only the mock `analysis.json` update — the render script itself is unchanged. All existing shell scripts (`extract-metrics.sh`, `detect-patterns.sh`, `render-html.sh`) are untouched.

**Constraint:** The e2e test (`tests/test-e2e.sh`) must still pass. It checks only: file presence (`index.html`, `styles.css`, `scripts.js`, `data.json`, `transcript.jsonl`) and round counts (1 after first render, 2 after re-render). It does not assert analysis content. The only test file change is updating the mock `analysis.json` block to use the new schema.

---

## ID Contract

The following element IDs are defined in Task 2 (index.html) and referenced in Task 4 (scripts.js). They must match exactly:

| ID | Purpose |
|----|---------|
| `session-id` | Session ID in top bar |
| `theme-toggle` | Dark/light toggle button |
| `generated-at` | Footer timestamp |
| `page-title` | H1 task title |
| `header-stat-workspace` | Header stat: workspace/session |
| `header-stat-messages` | Header stat: session message count |
| `header-stat-files` | Header stat: files changed |
| `header-stat-artifacts` | Header stat: proof artifact count |
| `verdict-banner` | Verdict banner (pass/fail/unknown class) |
| `verdict-icon` | Verdict icon character |
| `verdict-text` | Verdict text |
| `verdict-detail` | Verdict summary text |
| `tab-nav` | Sticky tab navigation container |
| `btn-show-all` | "Show all" button |
| `btn-focus-current` | "Focus current section" button |
| `stats-row` | Session metrics row |
| `timeline-bar` | Phase timeline bar |
| `timeline-legend` | Phase timeline legend |
| `flags-row` | Heuristic flags row |
| `panel-summary` | Summary tab panel |
| `panel-proof` | Proof tab panel |
| `panel-tests-existing` | Tests: Existing tab panel |
| `panel-tests-new` | Tests: New tab panel |
| `panel-friction` | Friction tab panel |
| `panel-diff` | Diff tab panel |
| `panel-repo-improvements` | Repo Improvements tab panel |
| `panel-user-improvements` | User Improvements tab panel |
| `session-artifacts` | Session artifacts section (always visible) |
| `verdict-statement` | Italic closing verdict statement |
| `transcript-container` | Full transcript inner container |
| `rounds-section` | Round picker section |
| `rounds-nav` | Round picker buttons |
| `screenshots-section` | Screenshots section (shown when present) |
| `screenshot-grid` | Screenshot grid |

---

## Task 1: Update analysis.json Schema

**Files:**
- Edit: `skills/generate/SKILL.md` — replace Step 4 with new schema
- Edit: `tests/test-e2e.sh` — replace mock analysis.json block

### Why the e2e test still passes

The test checks only:
1. `metrics.json` exists and has `totalTokens > 0` (unchanged)
2. `patterns.json` exists and has `falseCompletions | length >= 1` (unchanged)
3. `index.html`, `styles.css`, `scripts.js`, `data.json`, `transcript.jsonl` exist (unchanged — render-html.sh behavior is unchanged)
4. `rounds | length == 1` after first render, `2` after re-render (unchanged)

No assertion touches analysis content.

- [ ] **Step 1: Replace Step 4 in `skills/generate/SKILL.md`**

Replace the existing Step 4 block (lines 60–73) with:

```markdown
## Step 4: Analyze (if enabled)

Check if analysis is enabled (plugin config `analysis` option, default true).

If enabled, read the transcript, metrics.json, and patterns.json. Write `${PACK_DIR}/analysis.json` with this schema:

```json
{
  "title": "Short task description for page heading (1 sentence, no period)",
  "highlights": {
    "completionStatus": { "label": "Completion below", "color": "green", "notes": "One sentence on what was achieved" },
    "bestProof": { "badges": ["Screenshots", "Passing"], "note": "One sentence on strongest evidence type" },
    "strongestEvidence": "One sentence naming the single most convincing proof point",
    "mainRisk": "One sentence on the biggest remaining uncertainty or gap"
  },
  "summary": {
    "whatChanged": ["bullet: what changed in the extension/codebase", "..."],
    "whatTranscriptProves": ["point: what the session transcript directly demonstrates", "..."],
    "whatStillNotProven": ["gap: what was not verified or remains uncertain", "..."]
  },
  "proof": {
    "artifactInventory": [
      {"name": "Transcript", "path": "transcript.jsonl", "type": "transcript", "description": "Primary source for commands, failures, and outputs"}
    ],
    "evidenceTable": [
      {"point": "evidence point", "where": "transcript line / command / file", "whyItMatters": "why this evidence is significant"}
    ],
    "transcriptExcerpts": ["verbatim or paraphrased high-signal line from transcript", "..."]
  },
  "testsExisting": {
    "narrative": "Paragraph describing what existing tests cover and what was validated.",
    "validationTable": [
      {"validation": "command or test name", "observedResult": "what happened", "interpretation": "what this means"}
    ],
    "coveredWell": ["area covered by existing tests", "..."],
    "notCovered": ["gap in test coverage", "..."]
  },
  "testsNew": {
    "narrative": "Paragraph describing any new tests added.",
    "newTests": ["test name or description", "..."]
  },
  "frictionLog": [
    {"friction": "what slowed things down", "evidence": "specific transcript moment or pattern", "type": "tooling|structure|naming|docs|other", "resolution": "how it was resolved or what the impact was"}
  ],
  "diff": {
    "artifactStatus": { "hasDiffStat": false, "hasDiffPatch": false, "note": "Why diff artifacts are absent or what they show" },
    "filesChanged": [{"file": "path/to/file", "description": "what changed and why"}],
    "changeTable": [{"area": "logical area changed", "evidenceInTranscript": "command or message proving this", "observedEffect": "what the change does"}],
    "representativeCommands": ["git commit -m ...", "npm test", "..."]
  },
  "repoImprovements": [
    {"title": "Short title for improvement", "detail": "Full paragraph explaining the improvement and its impact."}
  ],
  "userImprovements": [
    {"title": "Short title for improvement", "detail": "Full paragraph explaining the improvement and its impact."}
  ],
  "promptPattern": "Example prompt that would have reduced friction — include file names and context clues that would have front-loaded the right information.",
  "sessionArtifacts": [
    {"name": "artifact name", "path": "relative/path/in/pack", "description": "what this artifact contains"}
  ],
  "verdictStatement": "Closing italic sentence summarizing the session outcome and its trustworthiness as evidence."
}
```

Be specific and actionable. Reference actual files, patterns, and moments from the transcript. Do not include empty arrays or null fields — omit sections for which there is no data.
```

- [ ] **Step 2: Replace mock analysis in `tests/test-e2e.sh`**

Replace the Step 4 block (lines 89–99):

```bash
# Step 4: Create mock analysis
echo ""
echo "--- Step 4: Mock analysis ---"
cat > "$TEST_DIR/$SESSION_ID/analysis.json" << 'JSON'
{
  "title": "Fix auth token expiry edge case in login.ts",
  "highlights": {
    "completionStatus": { "label": "Complete", "color": "green", "notes": "Bug fixed and all tests pass including midnight edge case" },
    "bestProof": { "badges": ["Passing Tests"], "note": "All 8 tests in auth.test.ts passed after fix" },
    "strongestEvidence": "Test suite output showing 8/8 pass after boundary condition fix",
    "mainRisk": "No integration test covering the token refresh path under load"
  },
  "summary": {
    "whatChanged": ["Fixed < to <= in token expiry comparison in login.ts", "Added boundary condition handling for midnight edge case"],
    "whatTranscriptProves": ["Agent identified root cause correctly on first read", "False completion detected — agent claimed done before edge case was fixed"],
    "whatStillNotProven": ["No load test for concurrent token refresh", "Only unit tests run, no e2e auth flow"]
  },
  "proof": {
    "artifactInventory": [
      {"name": "Transcript", "path": "transcript.jsonl", "type": "transcript", "description": "Primary source for commands, failures, and outputs"}
    ],
    "evidenceTable": [
      {"point": "Bug root cause identified", "where": "turn 4: agent identifies < vs <= comparison", "whyItMatters": "Shows agent understood the problem correctly"},
      {"point": "False completion", "where": "turn 5: agent said Done but edge case still failed", "whyItMatters": "Demonstrates need for edge case tests in spec"}
    ],
    "transcriptExcerpts": ["Found it. The comparison uses < instead of <=.", "Fixed. All tests pass including the midnight edge case."]
  },
  "testsExisting": {
    "narrative": "auth.test.ts covered the main token expiry path but lacked a boundary test for midnight. The edge case test was identified by the user, not the agent.",
    "validationTable": [
      {"validation": "auth.test.ts", "observedResult": "8 passed", "interpretation": "All existing tests plus new edge case pass"}
    ],
    "coveredWell": ["Standard token expiry", "Invalid token rejection"],
    "notCovered": ["Concurrent refresh", "Token refresh under network failure"]
  },
  "testsNew": {
    "narrative": "No new test files were added. The midnight edge case was covered by an existing parameterized test that was previously skipped.",
    "newTests": []
  },
  "frictionLog": [
    {"friction": "Missing boundary test for midnight edge case", "evidence": "User had to point out the failing edge case after agent claimed completion", "type": "docs", "resolution": "Edge case fixed, but test was user-identified not agent-identified"}
  ],
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
echo "  PASS"
```

- [ ] **Step 3: Run e2e test to confirm it still passes**

```bash
bash /Users/jasonsmith/Code/eval-pack/tests/test-e2e.sh
```

Expected output: `=== ALL TESTS PASSED ===`

- [ ] **Step 4: Commit**

```bash
cd /Users/jasonsmith/Code/eval-pack
git add skills/generate/SKILL.md tests/test-e2e.sh
git commit -m "feat: update analysis.json schema to v2 structured format with 8 reporting dimensions"
```

---

## Task 2: New `templates/html/index.html`

**Files:**
- Replace: `templates/html/index.html`

Complete replacement. All element IDs from the ID Contract table are present. The old 3-tab analysis section is removed. The new structure is: top-bar → page-header → verdict-banner → metrics/flags area → sticky tab-nav → 8 tab panels → session-artifacts (always visible) → verdict-statement → transcript (collapsible) → rounds-section → footer.

- [ ] **Step 1: Write `templates/html/index.html`**

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

  <!-- Top Bar -->
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

    <!-- Page Header: task title + 4 header stats -->
    <section class="page-header" id="page-header">
      <h2 class="page-title" id="page-title"></h2>
      <div class="header-stats">
        <div class="header-stat" id="header-stat-workspace">
          <div class="header-stat-value" id="header-stat-workspace-value"></div>
          <div class="header-stat-label">Workspace</div>
        </div>
        <div class="header-stat" id="header-stat-messages">
          <div class="header-stat-value" id="header-stat-messages-value"></div>
          <div class="header-stat-label">Session Messages</div>
        </div>
        <div class="header-stat" id="header-stat-files">
          <div class="header-stat-value" id="header-stat-files-value"></div>
          <div class="header-stat-label">Files Changed</div>
        </div>
        <div class="header-stat" id="header-stat-artifacts">
          <div class="header-stat-value" id="header-stat-artifacts-value"></div>
          <div class="header-stat-label">Proof Artifacts</div>
        </div>
      </div>
    </section>

    <!-- Verdict Banner -->
    <section class="verdict-banner" id="verdict-banner">
      <div class="verdict-icon" id="verdict-icon"></div>
      <div class="verdict-text" id="verdict-text"></div>
      <div class="verdict-detail" id="verdict-detail"></div>
    </section>

    <!-- Screenshots / Visual Evidence (shown only when screenshots present) -->
    <section class="card" id="screenshots-section" style="display:none;">
      <h2 class="card-title">Visual Evidence</h2>
      <div class="screenshot-grid" id="screenshot-grid"></div>
    </section>

    <!-- Session Metrics (always visible) -->
    <section class="card" id="stats-card">
      <h2 class="card-title">Session Metrics</h2>
      <div class="stats-row" id="stats-row"></div>
    </section>

    <!-- Phase Timeline (always visible) -->
    <section class="card" id="timeline-section">
      <h2 class="card-title">Phase Timeline</h2>
      <div class="timeline-bar" id="timeline-bar"></div>
      <div class="timeline-legend" id="timeline-legend"></div>
    </section>

    <!-- Heuristic Flags (always visible) -->
    <section class="card" id="flags-section">
      <h2 class="card-title">Heuristic Flags</h2>
      <div class="flags-row" id="flags-row"></div>
    </section>

    <!-- Sticky Tab Navigation -->
    <div class="tab-nav-wrapper">
      <nav class="tab-nav" id="tab-nav" role="tablist">
        <button class="tab-btn active" data-panel="summary" role="tab" aria-selected="true">Summary</button>
        <button class="tab-btn" data-panel="proof" role="tab" aria-selected="false">Proof</button>
        <button class="tab-btn" data-panel="tests-existing" role="tab" aria-selected="false">Tests: Existing</button>
        <button class="tab-btn" data-panel="tests-new" role="tab" aria-selected="false">Tests: New</button>
        <button class="tab-btn" data-panel="friction" role="tab" aria-selected="false">Friction</button>
        <button class="tab-btn" data-panel="diff" role="tab" aria-selected="false">Diff</button>
        <button class="tab-btn" data-panel="repo-improvements" role="tab" aria-selected="false">Repo Improvements</button>
        <button class="tab-btn" data-panel="user-improvements" role="tab" aria-selected="false">User Improvements</button>
        <div class="tab-nav-actions">
          <button class="tab-action-btn" id="btn-show-all">Show all</button>
          <button class="tab-action-btn" id="btn-focus-current">Focus current section</button>
        </div>
      </nav>
    </div>

    <!-- Tab Panels -->

    <!-- Summary: 3-column what changed / proves / not proven -->
    <section class="tab-panel card" id="panel-summary" role="tabpanel">
      <div class="three-col">
        <div class="three-col-item">
          <h3 class="three-col-heading">What changed in the extension</h3>
          <ul class="bullet-list" id="summary-what-changed"></ul>
        </div>
        <div class="three-col-item">
          <h3 class="three-col-heading">What the transcript proves</h3>
          <ul class="bullet-list" id="summary-what-proves"></ul>
        </div>
        <div class="three-col-item">
          <h3 class="three-col-heading">What is still not proven</h3>
          <ul class="bullet-list" id="summary-not-proven"></ul>
        </div>
      </div>
    </section>

    <!-- Proof: left content + right sidebar artifact inventory -->
    <section class="tab-panel card" id="panel-proof" role="tabpanel" style="display:none;">
      <div class="proof-layout">
        <div class="proof-main">
          <!-- Screenshots / video artifacts in proof context -->
          <div id="proof-screenshots-area"></div>

          <!-- Evidence table -->
          <h3 class="section-subheading">Evidence</h3>
          <table class="data-table" id="proof-evidence-table">
            <thead>
              <tr>
                <th>Evidence Point</th>
                <th>Where It Appeared</th>
                <th>Why It Matters</th>
              </tr>
            </thead>
            <tbody id="proof-evidence-tbody"></tbody>
          </table>

          <!-- High-signal transcript excerpts -->
          <h3 class="section-subheading">High-Signal Transcript Excerpts</h3>
          <ul class="excerpt-list" id="proof-excerpts"></ul>
        </div>
        <aside class="proof-sidebar">
          <h3 class="sidebar-heading">Artifact Inventory</h3>
          <ul class="artifact-inventory" id="artifact-inventory"></ul>
        </aside>
      </div>
    </section>

    <!-- Tests: Existing -->
    <section class="tab-panel card" id="panel-tests-existing" role="tabpanel" style="display:none;">
      <p class="narrative" id="tests-existing-narrative"></p>

      <h3 class="section-subheading">Validation</h3>
      <table class="data-table" id="tests-existing-table">
        <thead>
          <tr>
            <th>Validation</th>
            <th>Observed Result</th>
            <th>Interpretation</th>
          </tr>
        </thead>
        <tbody id="tests-existing-tbody"></tbody>
      </table>

      <div class="two-col-grid">
        <div class="two-col-item">
          <h3 class="two-col-heading covered-heading">What covered well</h3>
          <ul class="bullet-list" id="tests-covered-well"></ul>
        </div>
        <div class="two-col-item">
          <h3 class="two-col-heading gap-heading">What not covered</h3>
          <ul class="bullet-list" id="tests-not-covered"></ul>
        </div>
      </div>
    </section>

    <!-- Tests: New -->
    <section class="tab-panel card" id="panel-tests-new" role="tabpanel" style="display:none;">
      <p class="narrative" id="tests-new-narrative"></p>
      <ul class="bullet-list" id="tests-new-list"></ul>
    </section>

    <!-- Friction -->
    <section class="tab-panel card" id="panel-friction" role="tabpanel" style="display:none;">
      <table class="data-table" id="friction-table">
        <thead>
          <tr>
            <th>Friction</th>
            <th>Evidence</th>
            <th>Type</th>
            <th>Resolution / Impact</th>
          </tr>
        </thead>
        <tbody id="friction-tbody"></tbody>
      </table>
    </section>

    <!-- Diff -->
    <section class="tab-panel card" id="panel-diff" role="tabpanel" style="display:none;">
      <div class="diff-artifact-status" id="diff-artifact-status"></div>

      <h3 class="section-subheading">Files Evidenced as Changed</h3>
      <ul class="files-changed-list" id="diff-files-changed"></ul>

      <h3 class="section-subheading">Change Evidence</h3>
      <table class="data-table" id="diff-change-table">
        <thead>
          <tr>
            <th>Area</th>
            <th>Evidence in Transcript</th>
            <th>Observed Effect</th>
          </tr>
        </thead>
        <tbody id="diff-change-tbody"></tbody>
      </table>

      <h3 class="section-subheading">Representative Commands</h3>
      <pre class="code-block" id="diff-commands"></pre>
    </section>

    <!-- Repo Improvements -->
    <section class="tab-panel card" id="panel-repo-improvements" role="tabpanel" style="display:none;">
      <ol class="improvements-list" id="repo-improvements-list"></ol>
    </section>

    <!-- User Improvements -->
    <section class="tab-panel card" id="panel-user-improvements" role="tabpanel" style="display:none;">
      <ol class="improvements-list" id="user-improvements-list"></ol>
      <div id="prompt-pattern-area" style="display:none;">
        <h3 class="section-subheading">Prompt pattern that would have reduced friction</h3>
        <pre class="code-block prompt-pattern" id="prompt-pattern"></pre>
      </div>
    </section>

    <!-- Session Artifacts (always visible, below all panels) -->
    <section class="card" id="session-artifacts">
      <h2 class="card-title">Session Artifacts</h2>
      <ul class="session-artifacts-list" id="session-artifacts-list"></ul>
    </section>

    <!-- Verdict Statement -->
    <section class="card verdict-statement-card" id="verdict-statement-card" style="display:none;">
      <p class="verdict-statement" id="verdict-statement"></p>
    </section>

    <!-- Full Transcript (collapsible) -->
    <section class="card" id="transcript-section">
      <details class="collapsible">
        <summary class="card-title collapsible-trigger">Full Transcript</summary>
        <div class="transcript-container" id="transcript-container"></div>
      </details>
    </section>

    <!-- Round picker (shown only when >1 round) -->
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

- [ ] **Step 2: Commit**

```bash
cd /Users/jasonsmith/Code/eval-pack
git add templates/html/index.html
git commit -m "feat(html): replace index.html with v2 tab-navigated layout — 8 panels, header stats, artifact inventory"
```

---

## Task 3: New `templates/html/styles.css`

**Files:**
- Replace: `templates/html/styles.css`

Complete replacement. All existing styles are preserved (theme tokens, verdict banner, cards, stats-row, timeline, flags, transcript turns, screenshots, modal, rounds, dark/light toggle, footer, responsive). New styles added for: tab-nav (sticky), tab-panel, page-header, header-stats, three-col, proof-layout with sidebar, data-table, excerpt-list, two-col-grid, improvements-list, diff-artifact-status, code-block, prompt-pattern, session-artifacts-list, artifact-inventory, verdict-statement.

- [ ] **Step 1: Write `templates/html/styles.css`**

```css
/* ===== Reset ===== */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

/* ===== Theme Tokens ===== */
:root {
  --bg: #0a0a0a;
  --bg-card: #111111;
  --bg-card-hover: #1a1a1a;
  --bg-code: #0d0d0d;
  --border: #2a2a2a;
  --text: #ededed;
  --text-secondary: #888888;
  --text-muted: #555555;
  --accent: #0070f3;
  --green: #17b169;
  --red: #e5484d;
  --amber: #f5a623;
  --radius: 8px;
  --font: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  --font-mono: 'SF Mono', 'Fira Code', 'Fira Mono', Menlo, monospace;
  --tab-nav-height: 48px;
}

[data-theme="light"] {
  --bg: #fafafa;
  --bg-card: #ffffff;
  --bg-card-hover: #f5f5f5;
  --bg-code: #f3f3f3;
  --border: #eaeaea;
  --text: #171717;
  --text-secondary: #666666;
  --text-muted: #999999;
}

/* ===== Base ===== */
body {
  background: var(--bg);
  color: var(--text);
  font-family: var(--font);
  line-height: 1.6;
  min-height: 100vh;
}

/* ===== Top Bar ===== */
.top-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 24px;
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  background: var(--bg);
  z-index: 200;
}

.top-bar-left { display: flex; align-items: center; gap: 16px; }
.logo { font-size: 15px; font-weight: 600; letter-spacing: -0.3px; }
.session-id { font-size: 12px; color: var(--text-secondary); font-family: var(--font-mono); }

.theme-toggle {
  background: none;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text);
  cursor: pointer;
  padding: 5px 10px;
  font-size: 15px;
  line-height: 1;
}

[data-theme="dark"] .theme-icon-light { display: none; }
[data-theme="light"] .theme-icon-dark { display: none; }

/* ===== Container ===== */
.container {
  max-width: 1100px;
  margin: 0 auto;
  padding: 24px 24px 48px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* ===== Page Header ===== */
.page-header {
  padding: 20px 0 8px;
}

.page-title {
  font-size: 22px;
  font-weight: 700;
  letter-spacing: -0.5px;
  margin-bottom: 16px;
  color: var(--text);
}

.header-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.header-stat {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 16px;
}

.header-stat-value {
  font-size: 20px;
  font-weight: 700;
  font-family: var(--font-mono);
  color: var(--accent);
  line-height: 1.2;
}

.header-stat-label {
  font-size: 11px;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-top: 4px;
}

/* ===== Verdict Banner ===== */
.verdict-banner {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 18px 22px;
  border-radius: var(--radius);
  border: 1px solid var(--border);
}

.verdict-banner.pass {
  background: linear-gradient(135deg, rgba(23, 177, 105, 0.08), transparent);
  border-color: var(--green);
}

.verdict-banner.fail {
  background: linear-gradient(135deg, rgba(229, 72, 77, 0.08), transparent);
  border-color: var(--red);
}

.verdict-banner.unknown {
  background: linear-gradient(135deg, rgba(245, 166, 35, 0.08), transparent);
  border-color: var(--amber);
}

.verdict-icon { font-size: 28px; flex-shrink: 0; }
.verdict-text { font-size: 18px; font-weight: 600; }
.verdict-detail { font-size: 13px; color: var(--text-secondary); margin-left: auto; }

/* ===== Cards ===== */
.card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px 24px;
}

.card-title {
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.6px;
  color: var(--text-secondary);
  margin-bottom: 14px;
}

/* ===== Stats Row ===== */
.stats-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
  gap: 16px;
}

.stat-item { text-align: center; }
.stat-value { font-size: 22px; font-weight: 700; font-family: var(--font-mono); }
.stat-label { font-size: 11px; color: var(--text-secondary); margin-top: 4px; }

/* ===== Phase Timeline ===== */
.timeline-bar {
  display: flex;
  height: 30px;
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
  min-width: 36px;
}

.timeline-segment.understanding { background: #6366f1; }
.timeline-segment.planning { background: #0070f3; }
.timeline-segment.implementation { background: #17b169; }
.timeline-segment.testing { background: #f5a623; }
.timeline-segment.fixing { background: #e5484d; }
.timeline-segment.false-completion {
  background: repeating-linear-gradient(45deg, var(--amber), var(--amber) 4px, transparent 4px, transparent 8px);
}

.timeline-legend {
  display: flex;
  gap: 14px;
  margin-top: 10px;
  flex-wrap: wrap;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  color: var(--text-secondary);
}

.legend-dot {
  width: 9px;
  height: 9px;
  border-radius: 2px;
  flex-shrink: 0;
}

/* ===== Flags ===== */
.flags-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.flag-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 11px;
  border-radius: 20px;
  font-size: 13px;
  font-weight: 500;
}

.flag-chip.red { background: rgba(229, 72, 77, 0.12); color: var(--red); border: 1px solid rgba(229, 72, 77, 0.25); }
.flag-chip.amber { background: rgba(245, 166, 35, 0.12); color: var(--amber); border: 1px solid rgba(245, 166, 35, 0.25); }
.flag-chip.green { background: rgba(23, 177, 105, 0.12); color: var(--green); border: 1px solid rgba(23, 177, 105, 0.25); }

/* ===== Sticky Tab Navigation ===== */
.tab-nav-wrapper {
  position: sticky;
  top: calc(var(--tab-nav-height) + 14px); /* below top-bar */
  z-index: 150;
  background: var(--bg);
  border-bottom: 1px solid var(--border);
  margin: 0 -24px;
  padding: 0 24px;
}

.tab-nav {
  display: flex;
  align-items: center;
  gap: 0;
  overflow-x: auto;
  scrollbar-width: none;
  -ms-overflow-style: none;
}

.tab-nav::-webkit-scrollbar { display: none; }

.tab-btn {
  flex-shrink: 0;
  background: none;
  border: none;
  color: var(--text-secondary);
  padding: 12px 16px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  border-bottom: 2px solid transparent;
  transition: color 0.12s, border-color 0.12s;
  white-space: nowrap;
}

.tab-btn:hover { color: var(--text); }
.tab-btn.active { color: var(--text); border-bottom-color: var(--accent); }

.tab-nav-actions {
  margin-left: auto;
  display: flex;
  gap: 8px;
  padding: 8px 0;
  flex-shrink: 0;
}

.tab-action-btn {
  background: none;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text-secondary);
  padding: 4px 10px;
  font-size: 12px;
  cursor: pointer;
  transition: color 0.12s, border-color 0.12s;
}

.tab-action-btn:hover { color: var(--text); border-color: var(--text-secondary); }

/* ===== Tab Panels ===== */
.tab-panel { scroll-margin-top: 96px; }

/* ===== Summary: Three Columns ===== */
.three-col {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
}

.three-col-heading {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.4px;
  margin-bottom: 12px;
}

.bullet-list {
  list-style: none;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.bullet-list li {
  font-size: 14px;
  line-height: 1.5;
  padding-left: 16px;
  position: relative;
  color: var(--text);
}

.bullet-list li::before {
  content: '·';
  position: absolute;
  left: 0;
  color: var(--text-muted);
  font-size: 18px;
  line-height: 1.2;
}

/* ===== Proof: Left + Sidebar ===== */
.proof-layout {
  display: grid;
  grid-template-columns: 1fr 280px;
  gap: 24px;
  align-items: start;
}

.proof-main { min-width: 0; }

.proof-sidebar {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px;
  position: sticky;
  top: 120px;
}

.sidebar-heading {
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-secondary);
  margin-bottom: 12px;
}

.artifact-inventory {
  list-style: none;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.artifact-inventory li {
  font-size: 13px;
  line-height: 1.4;
}

.artifact-name {
  font-weight: 600;
  color: var(--text);
}

.artifact-path {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--accent);
  display: block;
  margin: 2px 0;
  word-break: break-all;
}

.artifact-desc {
  color: var(--text-secondary);
  font-size: 12px;
}

/* ===== Section Subheadings ===== */
.section-subheading {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.4px;
  margin: 20px 0 10px;
}

.section-subheading:first-child { margin-top: 0; }

/* ===== Data Tables ===== */
.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  margin-bottom: 8px;
}

.data-table th {
  text-align: left;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-secondary);
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
}

.data-table td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  vertical-align: top;
  color: var(--text);
  line-height: 1.5;
}

.data-table tbody tr:last-child td { border-bottom: none; }

.data-table tbody tr:hover td {
  background: var(--bg-card-hover);
}

/* ===== Excerpt List ===== */
.excerpt-list {
  list-style: none;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.excerpt-list li {
  font-size: 13px;
  font-family: var(--font-mono);
  background: var(--bg-code);
  border-left: 3px solid var(--accent);
  padding: 10px 14px;
  border-radius: 0 4px 4px 0;
  color: var(--text);
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}

/* ===== Two-column grid (tests covered / not covered) ===== */
.two-col-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  margin-top: 20px;
}

.two-col-heading {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.4px;
  margin-bottom: 10px;
}

.covered-heading { color: var(--green); }
.gap-heading { color: var(--amber); }

/* ===== Narrative ===== */
.narrative {
  font-size: 14px;
  line-height: 1.7;
  color: var(--text);
  margin-bottom: 16px;
}

/* ===== Diff Section ===== */
.diff-artifact-status {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.diff-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 11px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 500;
}

.diff-badge.present { background: rgba(23, 177, 105, 0.12); color: var(--green); border: 1px solid rgba(23, 177, 105, 0.25); }
.diff-badge.absent { background: rgba(136, 136, 136, 0.1); color: var(--text-secondary); border: 1px solid var(--border); }

.files-changed-list {
  list-style: none;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 8px;
}

.files-changed-list li {
  font-size: 13px;
  display: flex;
  gap: 10px;
  align-items: baseline;
}

.files-changed-list .file-path {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--accent);
  flex-shrink: 0;
}

.files-changed-list .file-desc {
  color: var(--text-secondary);
  font-size: 13px;
}

/* ===== Code Block ===== */
.code-block {
  background: var(--bg-code);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 14px 16px;
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.6;
  color: var(--text);
  overflow-x: auto;
  white-space: pre;
  margin-bottom: 8px;
}

.prompt-pattern {
  border-left: 3px solid var(--accent);
  border-radius: 0 4px 4px 0;
  white-space: pre-wrap;
  word-break: break-word;
}

/* ===== Improvements List ===== */
.improvements-list {
  list-style: none;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 20px;
  counter-reset: improvements;
}

.improvements-list li {
  display: grid;
  grid-template-columns: 28px 1fr;
  gap: 12px;
  counter-increment: improvements;
}

.improvements-list li::before {
  content: counter(improvements);
  font-size: 18px;
  font-weight: 700;
  font-family: var(--font-mono);
  color: var(--text-muted);
  line-height: 1.4;
}

.improvement-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
  margin-bottom: 6px;
}

.improvement-detail {
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-secondary);
}

/* ===== Session Artifacts ===== */
.session-artifacts-list {
  list-style: none;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.session-artifacts-list li {
  font-size: 13px;
  display: flex;
  gap: 8px;
  align-items: baseline;
}

.session-artifacts-list .artifact-name {
  font-weight: 500;
  flex-shrink: 0;
}

.session-artifacts-list .artifact-path {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--accent);
  flex-shrink: 0;
  display: inline;
}

.session-artifacts-list .artifact-desc {
  color: var(--text-secondary);
}

/* ===== Verdict Statement ===== */
.verdict-statement-card {
  border-color: var(--border);
}

.verdict-statement {
  font-size: 14px;
  font-style: italic;
  line-height: 1.7;
  color: var(--text-secondary);
}

/* ===== Transcript ===== */
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
  padding: 10px 14px;
  border-left: 3px solid var(--border);
  margin-bottom: 8px;
}

.turn.human { border-left-color: var(--accent); }
.turn.assistant { border-left-color: var(--green); }

.turn-header {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.turn-role { font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }
.turn-content { font-size: 13px; white-space: pre-wrap; word-break: break-word; }

.turn-content pre {
  background: var(--bg-code);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 10px;
  overflow-x: auto;
  font-family: var(--font-mono);
  font-size: 12px;
  margin: 6px 0;
}

/* ===== Screenshots ===== */
.screenshot-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
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
  padding: 7px 12px;
  font-size: 12px;
  color: var(--text-secondary);
  background: var(--bg);
}

/* ===== Screenshot Modal ===== */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.88);
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

/* ===== Rounds Nav ===== */
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

/* ===== Footer ===== */
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

/* ===== Responsive ===== */
@media (max-width: 900px) {
  .proof-layout { grid-template-columns: 1fr; }
  .proof-sidebar { position: static; }
  .three-col { grid-template-columns: 1fr; }
  .header-stats { grid-template-columns: repeat(2, 1fr); }
}

@media (max-width: 640px) {
  .container { padding: 12px 12px 32px; }
  .stats-row { grid-template-columns: repeat(2, 1fr); }
  .verdict-banner { flex-wrap: wrap; }
  .verdict-detail { margin-left: 0; width: 100%; }
  .two-col-grid { grid-template-columns: 1fr; }
  .header-stats { grid-template-columns: repeat(2, 1fr); }
  .tab-nav-wrapper { margin: 0 -12px; padding: 0 12px; }
}
```

- [ ] **Step 2: Commit**

```bash
cd /Users/jasonsmith/Code/eval-pack
git add templates/html/styles.css
git commit -m "feat(css): replace styles.css with v2 — tab-nav, proof-layout, data-tables, improvements-list, all new section styles"
```

---

## Task 4: New `templates/html/scripts.js`

**Files:**
- Replace: `templates/html/scripts.js`

Complete replacement. Renders all 8 tabs from `analysis` data + metrics from `round.metrics` + `round.patterns`. Preserves all existing helpers. All element IDs match exactly what Task 2 defines.

### ID Usage Map (scripts.js → index.html)

| Script reference | HTML id |
|-----------------|---------|
| `document.getElementById('session-id')` | `session-id` |
| `document.getElementById('generated-at')` | `generated-at` |
| `document.getElementById('theme-toggle')` | `theme-toggle` |
| `document.getElementById('page-title')` | `page-title` |
| `document.getElementById('header-stat-workspace-value')` | `header-stat-workspace-value` |
| `document.getElementById('header-stat-messages-value')` | `header-stat-messages-value` |
| `document.getElementById('header-stat-files-value')` | `header-stat-files-value` |
| `document.getElementById('header-stat-artifacts-value')` | `header-stat-artifacts-value` |
| `document.getElementById('verdict-banner')` | `verdict-banner` |
| `document.getElementById('verdict-icon')` | `verdict-icon` |
| `document.getElementById('verdict-text')` | `verdict-text` |
| `document.getElementById('verdict-detail')` | `verdict-detail` |
| `document.getElementById('stats-row')` | `stats-row` |
| `document.getElementById('timeline-bar')` | `timeline-bar` |
| `document.getElementById('timeline-legend')` | `timeline-legend` |
| `document.getElementById('flags-row')` | `flags-row` |
| `document.getElementById('screenshots-section')` | `screenshots-section` |
| `document.getElementById('screenshot-grid')` | `screenshot-grid` |
| `document.getElementById('summary-what-changed')` | `summary-what-changed` |
| `document.getElementById('summary-what-proves')` | `summary-what-proves` |
| `document.getElementById('summary-not-proven')` | `summary-not-proven` |
| `document.getElementById('proof-evidence-tbody')` | `proof-evidence-tbody` |
| `document.getElementById('proof-excerpts')` | `proof-excerpts` |
| `document.getElementById('artifact-inventory')` | `artifact-inventory` |
| `document.getElementById('tests-existing-narrative')` | `tests-existing-narrative` |
| `document.getElementById('tests-existing-tbody')` | `tests-existing-tbody` |
| `document.getElementById('tests-covered-well')` | `tests-covered-well` |
| `document.getElementById('tests-not-covered')` | `tests-not-covered` |
| `document.getElementById('tests-new-narrative')` | `tests-new-narrative` |
| `document.getElementById('tests-new-list')` | `tests-new-list` |
| `document.getElementById('friction-tbody')` | `friction-tbody` |
| `document.getElementById('diff-artifact-status')` | `diff-artifact-status` |
| `document.getElementById('diff-files-changed')` | `diff-files-changed` |
| `document.getElementById('diff-change-tbody')` | `diff-change-tbody` |
| `document.getElementById('diff-commands')` | `diff-commands` |
| `document.getElementById('repo-improvements-list')` | `repo-improvements-list` |
| `document.getElementById('user-improvements-list')` | `user-improvements-list` |
| `document.getElementById('prompt-pattern-area')` | `prompt-pattern-area` |
| `document.getElementById('prompt-pattern')` | `prompt-pattern` |
| `document.getElementById('session-artifacts-list')` | `session-artifacts-list` |
| `document.getElementById('verdict-statement-card')` | `verdict-statement-card` |
| `document.getElementById('verdict-statement')` | `verdict-statement` |
| `document.getElementById('transcript-container')` | `transcript-container` |
| `document.getElementById('rounds-section')` | `rounds-section` |
| `document.getElementById('rounds-nav')` | `rounds-nav` |
| `document.querySelectorAll('[data-panel]')` | tab-btn elements in `tab-nav` |
| `document.getElementById('panel-' + panel)` | `panel-summary`, `panel-proof`, etc. |
| `document.getElementById('btn-show-all')` | `btn-show-all` |
| `document.getElementById('btn-focus-current')` | `btn-focus-current` |

- [ ] **Step 1: Write `templates/html/scripts.js`**

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

  // ── Theme toggle ──────────────────────────────────────────────────────────
  const toggle = document.getElementById('theme-toggle');
  const savedTheme = localStorage.getItem('eval-pack-theme');
  if (savedTheme) document.documentElement.setAttribute('data-theme', savedTheme);

  toggle.addEventListener('click', () => {
    const current = document.documentElement.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('eval-pack-theme', next);
  });

  // ── Session-level fields (outside rounds) ─────────────────────────────────
  document.getElementById('session-id').textContent = data.sessionId || '';
  document.getElementById('generated-at').textContent = data.generatedAt || '';

  // ── Tab navigation ────────────────────────────────────────────────────────
  const tabBtns = document.querySelectorAll('.tab-btn[data-panel]');
  let currentPanel = 'summary';

  function activatePanel(panel) {
    currentPanel = panel;
    tabBtns.forEach(btn => {
      const isActive = btn.dataset.panel === panel;
      btn.classList.toggle('active', isActive);
      btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
    });
    document.querySelectorAll('.tab-panel').forEach(el => {
      el.style.display = el.id === 'panel-' + panel ? '' : 'none';
    });
  }

  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => activatePanel(btn.dataset.panel));
  });

  document.getElementById('btn-show-all').addEventListener('click', () => {
    tabBtns.forEach(btn => btn.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(el => { el.style.display = ''; });
  });

  document.getElementById('btn-focus-current').addEventListener('click', () => {
    activatePanel(currentPanel);
  });

  // ── Main render ───────────────────────────────────────────────────────────
  function renderRound(roundIdx) {
    const round = getRound(roundIdx);
    const metrics = round.metrics || {};
    const patterns = round.patterns || {};
    const analysis = round.analysis || {};
    const testResults = round.testResults || {};

    renderPageHeader(analysis, metrics);
    renderVerdict(testResults);
    renderStats(metrics);
    renderFlags(patterns);
    renderScreenshots(round.screenshots || []);
    renderSummary(analysis.summary || {});
    renderProof(analysis.proof || {});
    renderTestsExisting(analysis.testsExisting || {});
    renderTestsNew(analysis.testsNew || {});
    renderFriction(analysis.frictionLog || []);
    renderDiff(analysis.diff || {});
    renderImprovements('repo-improvements-list', analysis.repoImprovements || []);
    renderImprovements('user-improvements-list', analysis.userImprovements || []);
    renderPromptPattern(analysis.promptPattern);
    renderSessionArtifacts(analysis.sessionArtifacts || []);
    renderVerdictStatement(analysis.verdictStatement);
  }

  // ── Page header ───────────────────────────────────────────────────────────
  function renderPageHeader(analysis, metrics) {
    const title = analysis.title || '';
    document.getElementById('page-title').textContent = title;
    if (title) document.title = 'Eval Pack — ' + title;

    document.getElementById('header-stat-workspace-value').textContent =
      (metrics.lastModel || metrics.model || 'N/A');
    document.getElementById('header-stat-messages-value').textContent =
      formatNumber(metrics.turnCount);
    document.getElementById('header-stat-files-value').textContent =
      formatNumber(metrics.filesChanged);
    const artifactCount = (analysis.proof && analysis.proof.artifactInventory)
      ? analysis.proof.artifactInventory.length
      : (analysis.sessionArtifacts ? analysis.sessionArtifacts.length : 0);
    document.getElementById('header-stat-artifacts-value').textContent =
      formatNumber(artifactCount);
  }

  // ── Verdict ───────────────────────────────────────────────────────────────
  function renderVerdict(testResults) {
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
  }

  // ── Session stats ─────────────────────────────────────────────────────────
  function renderStats(metrics) {
    const statsRow = document.getElementById('stats-row');
    const stats = [
      { value: metrics.lastModel || metrics.model || 'N/A', label: 'Model' },
      { value: formatNumber(metrics.totalTokens), label: 'Total Tokens' },
      { value: metrics.turnCount != null ? metrics.turnCount : 0, label: 'Turns' },
      { value: formatDuration(metrics.firstTimestamp, metrics.lastTimestamp), label: 'Duration' },
      { value: metrics.filesChanged != null ? metrics.filesChanged : 0, label: 'Files Changed' },
      { value: '+' + (metrics.insertions || 0) + ' / -' + (metrics.deletions || 0), label: 'Lines' },
    ];
    statsRow.innerHTML = stats.map(s =>
      '<div class="stat-item"><div class="stat-value">' + escapeHtml(String(s.value)) +
      '</div><div class="stat-label">' + escapeHtml(s.label) + '</div></div>'
    ).join('');
  }

  // ── Flags ─────────────────────────────────────────────────────────────────
  function renderFlags(patterns) {
    const flagsRow = document.getElementById('flags-row');
    const flags = patterns.flags || [];
    flagsRow.innerHTML = flags.map(f => {
      const countStr = f.count ? ' (' + f.count + ')' : '';
      return '<span class="flag-chip ' + escapeHtml(f.level || '') + '">' +
        escapeHtml(f.label || '') + escapeHtml(countStr) + '</span>';
    }).join('');
  }

  // ── Screenshots ───────────────────────────────────────────────────────────
  function renderScreenshots(screenshots) {
    const section = document.getElementById('screenshots-section');
    const grid = document.getElementById('screenshot-grid');
    if (!screenshots || screenshots.length === 0) { section.style.display = 'none'; return; }
    section.style.display = '';
    grid.innerHTML = '';
    screenshots.forEach(s => {
      const item = document.createElement('div');
      item.className = 'screenshot-item';
      const img = document.createElement('img');
      img.src = s.path;
      img.alt = s.label || '';
      img.loading = 'lazy';
      const label = document.createElement('div');
      label.className = 'screenshot-label';
      label.textContent = s.label || '';
      item.appendChild(img);
      item.appendChild(label);
      item.addEventListener('click', () => showModal(s.path));
      grid.appendChild(item);
    });
  }

  // ── Summary tab ───────────────────────────────────────────────────────────
  function renderSummary(summary) {
    renderBulletList('summary-what-changed', summary.whatChanged || []);
    renderBulletList('summary-what-proves', summary.whatTranscriptProves || []);
    renderBulletList('summary-not-proven', summary.whatStillNotProven || []);
  }

  function renderBulletList(id, items) {
    const el = document.getElementById(id);
    if (!el) return;
    if (!items || items.length === 0) {
      el.innerHTML = '<li><em style="color:var(--text-muted)">No data</em></li>';
      return;
    }
    el.innerHTML = items.map(item =>
      '<li>' + escapeHtml(String(item)) + '</li>'
    ).join('');
  }

  // ── Proof tab ─────────────────────────────────────────────────────────────
  function renderProof(proof) {
    // Artifact inventory (sidebar)
    const inventory = document.getElementById('artifact-inventory');
    const artifacts = proof.artifactInventory || [];
    if (artifacts.length === 0) {
      inventory.innerHTML = '<li style="color:var(--text-muted);font-size:13px">No artifacts catalogued</li>';
    } else {
      inventory.innerHTML = artifacts.map(a =>
        '<li>' +
        '<span class="artifact-name">' + escapeHtml(a.name || '') + '</span>' +
        (a.path ? '<span class="artifact-path">' + escapeHtml(a.path) + '</span>' : '') +
        (a.description ? '<span class="artifact-desc">' + escapeHtml(a.description) + '</span>' : '') +
        '</li>'
      ).join('');
    }

    // Evidence table
    const tbody = document.getElementById('proof-evidence-tbody');
    const evidence = proof.evidenceTable || [];
    if (evidence.length === 0) {
      tbody.innerHTML = '<tr><td colspan="3" style="color:var(--text-muted)">No evidence recorded</td></tr>';
    } else {
      tbody.innerHTML = evidence.map(e =>
        '<tr>' +
        '<td>' + escapeHtml(e.point || '') + '</td>' +
        '<td style="font-family:var(--font-mono);font-size:12px">' + escapeHtml(e.where || '') + '</td>' +
        '<td>' + escapeHtml(e.whyItMatters || '') + '</td>' +
        '</tr>'
      ).join('');
    }

    // Transcript excerpts
    const excerpts = document.getElementById('proof-excerpts');
    const ex = proof.transcriptExcerpts || [];
    if (ex.length === 0) {
      excerpts.innerHTML = '<li style="color:var(--text-muted)">No excerpts recorded</li>';
    } else {
      excerpts.innerHTML = ex.map(e => '<li>' + escapeHtml(String(e)) + '</li>').join('');
    }
  }

  // ── Tests: Existing tab ───────────────────────────────────────────────────
  function renderTestsExisting(te) {
    const narrative = document.getElementById('tests-existing-narrative');
    narrative.textContent = te.narrative || '';

    const tbody = document.getElementById('tests-existing-tbody');
    const rows = te.validationTable || [];
    if (rows.length === 0) {
      tbody.innerHTML = '<tr><td colspan="3" style="color:var(--text-muted)">No validation data</td></tr>';
    } else {
      tbody.innerHTML = rows.map(r =>
        '<tr>' +
        '<td style="font-family:var(--font-mono);font-size:12px">' + escapeHtml(r.validation || '') + '</td>' +
        '<td>' + escapeHtml(r.observedResult || '') + '</td>' +
        '<td>' + escapeHtml(r.interpretation || '') + '</td>' +
        '</tr>'
      ).join('');
    }

    renderBulletList('tests-covered-well', te.coveredWell || []);
    renderBulletList('tests-not-covered', te.notCovered || []);
  }

  // ── Tests: New tab ────────────────────────────────────────────────────────
  function renderTestsNew(tn) {
    document.getElementById('tests-new-narrative').textContent = tn.narrative || '';
    renderBulletList('tests-new-list', tn.newTests || []);
  }

  // ── Friction tab ──────────────────────────────────────────────────────────
  function renderFriction(frictionLog) {
    const tbody = document.getElementById('friction-tbody');
    if (!frictionLog || frictionLog.length === 0) {
      tbody.innerHTML = '<tr><td colspan="4" style="color:var(--text-muted)">No friction recorded</td></tr>';
      return;
    }
    tbody.innerHTML = frictionLog.map(f =>
      '<tr>' +
      '<td>' + escapeHtml(f.friction || '') + '</td>' +
      '<td style="font-size:12px;font-family:var(--font-mono)">' + escapeHtml(f.evidence || '') + '</td>' +
      '<td><span class="flag-chip amber" style="font-size:11px;padding:3px 8px">' + escapeHtml(f.type || '') + '</span></td>' +
      '<td>' + escapeHtml(f.resolution || '') + '</td>' +
      '</tr>'
    ).join('');
  }

  // ── Diff tab ──────────────────────────────────────────────────────────────
  function renderDiff(diff) {
    // Artifact status badges
    const statusEl = document.getElementById('diff-artifact-status');
    const artifactStatus = diff.artifactStatus || {};
    const badges = [
      { key: 'hasDiffStat', label: 'diff --stat' },
      { key: 'hasDiffPatch', label: 'diff patch' },
    ];
    statusEl.innerHTML = badges.map(b => {
      const present = artifactStatus[b.key];
      return '<span class="diff-badge ' + (present ? 'present' : 'absent') + '">' +
        (present ? '✓' : '✗') + ' ' + escapeHtml(b.label) + '</span>';
    }).join('') +
    (artifactStatus.note
      ? '<span style="font-size:13px;color:var(--text-secondary);margin-left:12px">' + escapeHtml(artifactStatus.note) + '</span>'
      : '');

    // Files changed
    const filesEl = document.getElementById('diff-files-changed');
    const files = diff.filesChanged || [];
    if (files.length === 0) {
      filesEl.innerHTML = '<li style="color:var(--text-muted);font-size:13px">No files recorded</li>';
    } else {
      filesEl.innerHTML = files.map(f =>
        '<li><span class="file-path">' + escapeHtml(f.file || '') + '</span>' +
        '<span class="file-desc">' + escapeHtml(f.description || '') + '</span></li>'
      ).join('');
    }

    // Change table
    const tbody = document.getElementById('diff-change-tbody');
    const changes = diff.changeTable || [];
    if (changes.length === 0) {
      tbody.innerHTML = '<tr><td colspan="3" style="color:var(--text-muted)">No change evidence</td></tr>';
    } else {
      tbody.innerHTML = changes.map(c =>
        '<tr>' +
        '<td>' + escapeHtml(c.area || '') + '</td>' +
        '<td style="font-size:12px;font-family:var(--font-mono)">' + escapeHtml(c.evidenceInTranscript || '') + '</td>' +
        '<td>' + escapeHtml(c.observedEffect || '') + '</td>' +
        '</tr>'
      ).join('');
    }

    // Representative commands
    const cmds = diff.representativeCommands || [];
    document.getElementById('diff-commands').textContent = cmds.length > 0
      ? cmds.join('\n')
      : '# No representative commands recorded';
  }

  // ── Improvements lists (repo + user) ─────────────────────────────────────
  function renderImprovements(listId, items) {
    const list = document.getElementById(listId);
    if (!items || items.length === 0) {
      list.innerHTML = '<li style="color:var(--text-muted);font-size:14px;grid-column:1/-1">No improvements recorded</li>';
      return;
    }
    list.innerHTML = items.map(item =>
      '<li>' +
      '<div></div>' + // counter column (CSS handles the number via counter())
      '<div>' +
      '<div class="improvement-title">' + escapeHtml(item.title || '') + '</div>' +
      '<div class="improvement-detail">' + escapeHtml(item.detail || '') + '</div>' +
      '</div>' +
      '</li>'
    ).join('');
  }

  // ── Prompt pattern ────────────────────────────────────────────────────────
  function renderPromptPattern(pattern) {
    const area = document.getElementById('prompt-pattern-area');
    const el = document.getElementById('prompt-pattern');
    if (!pattern) { area.style.display = 'none'; return; }
    area.style.display = '';
    el.textContent = pattern;
  }

  // ── Session artifacts ─────────────────────────────────────────────────────
  function renderSessionArtifacts(artifacts) {
    const list = document.getElementById('session-artifacts-list');
    if (!artifacts || artifacts.length === 0) {
      list.innerHTML = '<li style="color:var(--text-muted);font-size:13px">No artifacts recorded</li>';
      return;
    }
    list.innerHTML = artifacts.map(a =>
      '<li>' +
      '<span class="artifact-name">' + escapeHtml(a.name || '') + '</span>' +
      (a.path ? ' <span class="artifact-path">' + escapeHtml(a.path) + '</span>' : '') +
      (a.description ? ' <span class="artifact-desc">— ' + escapeHtml(a.description) + '</span>' : '') +
      '</li>'
    ).join('');
  }

  // ── Verdict statement ─────────────────────────────────────────────────────
  function renderVerdictStatement(statement) {
    const card = document.getElementById('verdict-statement-card');
    const el = document.getElementById('verdict-statement');
    if (!statement) { card.style.display = 'none'; return; }
    card.style.display = '';
    el.textContent = statement;
  }

  // ── Transcript ────────────────────────────────────────────────────────────
  function renderTranscript() {
    const container = document.getElementById('transcript-container');
    const transcript = data.transcript || [];
    container.innerHTML = transcript.map(turn => {
      const role = turn.type || 'unknown';
      const ts = turn.timestamp ? new Date(turn.timestamp).toLocaleTimeString() : '';
      const rawContent = typeof turn.content === 'string'
        ? turn.content
        : JSON.stringify(turn.content, null, 2);
      const content = escapeHtml(rawContent);
      return '<div class="turn ' + role + '">' +
        '<div class="turn-header">' +
        '<span class="turn-role">' + escapeHtml(role) + '</span>' +
        '<span>' + escapeHtml(ts) + '</span>' +
        '</div>' +
        '<div class="turn-content">' + content + '</div>' +
        '</div>';
    }).join('');
  }

  // ── Phase timeline ────────────────────────────────────────────────────────
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
      '<div class="timeline-segment ' + escapeHtml(p.className) + '" style="flex:' + p.weight + '">' +
      escapeHtml(p.name) + '</div>'
    ).join('');
    legend.innerHTML = phases.map(p =>
      '<div class="legend-item">' +
      '<div class="legend-dot" style="background:var(--' + escapeHtml(getPhaseColor(p.className)) + ')"></div>' +
      escapeHtml(p.name) + '</div>'
    ).join('');
  }

  // ── Rounds ────────────────────────────────────────────────────────────────
  function renderRounds() {
    if (!data.rounds || data.rounds.length <= 1) return;
    const section = document.getElementById('rounds-section');
    section.style.display = '';
    const nav = document.getElementById('rounds-nav');
    nav.innerHTML = data.rounds.map((_, i) =>
      '<button class="round-btn ' + (i === activeRound ? 'active' : '') +
      '" data-round="' + i + '">Round ' + (i + 1) + '</button>'
    ).join('');
    nav.querySelectorAll('.round-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        activeRound = parseInt(btn.dataset.round);
        renderRound(activeRound);
        renderRounds();
      });
    });
  }

  // ── Screenshot modal ──────────────────────────────────────────────────────
  window.showModal = function (src) {
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    const img = document.createElement('img');
    img.src = src;
    overlay.appendChild(img);
    overlay.addEventListener('click', () => overlay.remove());
    document.body.appendChild(overlay);
  };

  // ── Helpers ───────────────────────────────────────────────────────────────
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
    if (mins < 60) return mins + 'm';
    return Math.floor(mins / 60) + 'h ' + (mins % 60) + 'm';
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function renderMarkdown(text) {
    if (!text) return '';
    return escapeHtml(text)
      .replace(/^### (.+)$/gm, '<h4>$1</h4>')
      .replace(/^## (.+)$/gm, '<h3>$1</h3>')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\n/g, '<br>');
  }

  function getPhaseColor(className) {
    const map = {
      understanding: 'accent',
      planning: 'accent',
      implementation: 'green',
      testing: 'amber',
      fixing: 'red',
    };
    return map[className] || 'accent';
  }

  // ── Init ──────────────────────────────────────────────────────────────────
  renderRound(activeRound);
  renderTranscript();
  renderRounds();
  renderTimeline();
  activatePanel('summary');
})();
```

- [ ] **Step 2: Commit**

```bash
cd /Users/jasonsmith/Code/eval-pack
git add templates/html/scripts.js
git commit -m "feat(js): replace scripts.js with v2 — 8-tab renderer, header stats, all section renderers, tab switching"
```

---

## Task 5: End-to-End Test Run and Visual Verification

**Files:** None created — verification only

- [ ] **Step 1: Run the e2e test suite**

```bash
bash /Users/jasonsmith/Code/eval-pack/tests/test-e2e.sh
```

Expected output:
```
=== Eval Pack E2E Test ===
...
--- Step 1: Extract metrics --- PASS
--- Step 2: Detect patterns --- PASS
--- Step 3: Mock test results --- PASS
--- Step 4: Mock analysis --- PASS
--- Step 5: Render HTML --- PASS
--- Step 6: Test regeneration (round 2) --- PASS
=== ALL TESTS PASSED ===
```

If any step fails, check which step and fix per the guidance below.

**If Step 5 (Render HTML) fails:** Check that `render-html.sh` still reads `analysis.json` using `--slurpfile analysis` and embeds it in `round.analysis` — this is unchanged and the new schema is simply a richer JSON object that gets passed through without modification.

**If Step 6 (Regeneration) fails:** Check that `data.json` accumulates rounds correctly. The render script appends rounds to the existing array — this behavior is unchanged.

- [ ] **Step 2: Regenerate the actual session eval pack**

```bash
PLUGIN_ROOT="/Users/jasonsmith/Code/eval-pack"
SESSION_ID="9a73d2a3-b322-480f-b201-9f390f4936fc"
TRANSCRIPT="/Users/jasonsmith/.claude/projects/-Users-jasonsmith-Code-eval-pack/${SESSION_ID}.jsonl"
OUTPUT_DIR="${PLUGIN_ROOT}/.eval-packs"

"${PLUGIN_ROOT}/scripts/render-html.sh" "${OUTPUT_DIR}" "${SESSION_ID}" "${PLUGIN_ROOT}" "${TRANSCRIPT}"
```

This re-renders `index.html`, `styles.css`, and `scripts.js` in the existing pack from the updated templates. The existing `analysis.json` in the pack still uses the old 3-field schema — the new `scripts.js` will gracefully degrade (the old fields won't map to any rendered section, so panels will show "No data" states). This is acceptable for the visual verification step; to see full content you would re-run the generate skill against a new session using the new schema.

- [ ] **Step 3: Serve and open**

```bash
cd /Users/jasonsmith/Code/eval-pack/.eval-packs/9a73d2a3-b322-480f-b201-9f390f4936fc
python3 -m http.server 8765
```

Open `http://localhost:8765` in a browser.

**Visual verification checklist:**
- [ ] Page title visible in `<h2>` at top (will be empty since old analysis.json has no `title` field — expected)
- [ ] 4 header stats visible: Workspace (shows model), Session Messages (turn count), Files Changed, Proof Artifacts (shows 0 — expected with old analysis.json)
- [ ] Verdict banner renders correctly (pass/fail/unknown based on `test-results.json`)
- [ ] Session metrics row (6 stats) renders
- [ ] Phase timeline renders
- [ ] Heuristic flags render
- [ ] Sticky tab nav renders: 8 tabs + "Show all" + "Focus current section"
- [ ] Clicking each tab shows/hides its panel
- [ ] "Show all" makes all panels visible simultaneously
- [ ] "Focus current section" re-hides all but active panel
- [ ] Summary tab: three-column layout visible (columns will show "No data" bullets — expected)
- [ ] Proof tab: evidence table, excerpt list, sidebar artifact inventory visible (empty — expected)
- [ ] Tests: Existing tab: narrative + validation table + two-column grid visible
- [ ] Tests: New tab: narrative + list visible
- [ ] Friction tab: table visible
- [ ] Diff tab: badge row + files + change table + commands block visible
- [ ] Repo Improvements: numbered list visible
- [ ] User Improvements: numbered list + prompt pattern visible (hidden since no promptPattern)
- [ ] Session Artifacts section always visible at bottom
- [ ] Verdict statement card hidden (no verdictStatement in old analysis.json — expected)
- [ ] Full Transcript collapsible works
- [ ] Round picker shows "Round 2" (this session has 2 rounds)
- [ ] Dark/light theme toggle works, persists in localStorage
- [ ] Responsive: narrow the browser to 640px — header-stats go to 2-column, proof layout goes single-column

- [ ] **Step 4: Commit**

```bash
cd /Users/jasonsmith/Code/eval-pack
git add .eval-packs/9a73d2a3-b322-480f-b201-9f390f4936fc/index.html \
        .eval-packs/9a73d2a3-b322-480f-b201-9f390f4936fc/styles.css \
        .eval-packs/9a73d2a3-b322-480f-b201-9f390f4936fc/scripts.js \
        .eval-packs/9a73d2a3-b322-480f-b201-9f390f4936fc/data.json
git commit -m "chore: re-render existing eval pack with v2 HTML templates"
```

---

## Design Decisions and Trade-offs

**Why `activatePanel()` uses `panel-${name}` IDs instead of `data-tab` attributes**

The old code used `data-tab` on buttons and `id="tab-${tab}"` on content divs, with `document.querySelectorAll('.tab-content')` to hide all. The new design uses `data-panel` on buttons and `id="panel-${panel}"` on panels, with `document.querySelectorAll('.tab-panel')` to target panels. This avoids collision with the old `.tab-content` class (which no longer exists) and makes the "show all" / "focus" button logic clean.

**Why the `improvements-list` uses CSS counters instead of HTML `<li>` numbers**

The list uses `counter-reset` and `counter-increment` in CSS so the number renders as a large styled pseudo-element in a grid column, separate from the content column. This matches the reference design's numbered-list-with-detail-paragraph pattern cleanly without needing wrapper divs per-number.

**Why `renderMarkdown` is kept but not used in the new renderers**

The new schema provides structured data (arrays, tables), not Markdown blobs. `renderMarkdown` is preserved because it is an existing helper that may be useful if the generate skill ever produces hybrid content, and removing it would break any consumer that references it directly.

**Why `escapeHtml` now uses `String(str)` coercion**

The original `escapeHtml` assumed string input. In the new renderers, numbers (turn count, token count) are sometimes passed directly. Adding `String(str)` coercion prevents a `replace is not a function` error on numeric values without changing the function's external behavior for strings.

**Why the sticky tab nav uses `top: calc(var(--tab-nav-height) + 14px)`**

The top bar is sticky at `z-index: 200`. The tab nav is sticky just below it. The `--tab-nav-height: 48px` token is the top-bar height. The `+14px` is the padding offset. Without this, the tab nav would slide under the top bar.

**Why `proof-sidebar` uses `position: sticky; top: 120px`**

120px positions the sidebar below both the sticky top-bar and sticky tab-nav when the user scrolls through the proof panel. This matches the reference design where the artifact inventory stays in view as the user reads the evidence table and excerpts.

---

## Self-Review Checklist

**ID contract verified:**
- All IDs in the ID Contract table are present in Task 2 (index.html)
- All IDs in the ID Contract table are referenced in Task 4 (scripts.js) — cross-referenced in the ID Usage Map table
- No orphan IDs (IDs in HTML not referenced in JS, or JS references to IDs not in HTML)

**Schema contract verified:**
- Task 1 mock uses the exact schema structure that Task 4 reads
- All `analysis.*` field paths in Task 4 match the schema in Task 1: `analysis.title`, `analysis.summary.whatChanged`, `analysis.proof.artifactInventory`, `analysis.proof.evidenceTable`, `analysis.proof.transcriptExcerpts`, `analysis.testsExisting.narrative`, `analysis.testsExisting.validationTable`, `analysis.testsExisting.coveredWell`, `analysis.testsExisting.notCovered`, `analysis.testsNew.narrative`, `analysis.testsNew.newTests`, `analysis.frictionLog`, `analysis.diff.artifactStatus`, `analysis.diff.filesChanged`, `analysis.diff.changeTable`, `analysis.diff.representativeCommands`, `analysis.repoImprovements`, `analysis.userImprovements`, `analysis.promptPattern`, `analysis.sessionArtifacts`, `analysis.verdictStatement`

**Backward compatibility:**
- Old `analysis.json` with `{retrospective, friction, promptQuality}` will render gracefully — all analysis fields will fall back to empty arrays/strings and show "No data" states
- `metrics.lastModel` and `metrics.model` are both checked (the existing extract-metrics.sh uses `lastModel`, the old plan used `model`)
- `metrics.filesChanged` can be a number or come from `diff.filesChanged.length` — the header stat uses `metrics.filesChanged` directly for consistency with existing scripts

**e2e test compatibility:**
- The test only asserts: files exist, `rounds | length == 1`, `rounds | length == 2` after re-render
- The mock analysis.json in Task 1 is valid JSON matching the new schema
- `render-html.sh` is unchanged — it embeds `analysis.json` verbatim as `round.analysis`

**No placeholders:** Every code block is complete and executable.

---

### Critical Files for Implementation

- `/Users/jasonsmith/Code/eval-pack/skills/generate/SKILL.md`
- `/Users/jasonsmith/Code/eval-pack/templates/html/index.html`
- `/Users/jasonsmith/Code/eval-pack/templates/html/scripts.js`
- `/Users/jasonsmith/Code/eval-pack/templates/html/styles.css`
- `/Users/jasonsmith/Code/eval-pack/tests/test-e2e.sh`