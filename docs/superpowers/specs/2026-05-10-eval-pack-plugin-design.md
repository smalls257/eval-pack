# Eval Pack — Claude Code Plugin Design Spec

**Date:** 2026-05-10
**Status:** Draft
**Author:** Jason Smith + Claude

---

## Problem Statement

When AI agents produce code at high throughput, development teams lose visibility into three things:

1. **Quality signal** — did the agent's work actually pass muster? A failed test should be a failed eval.
2. **Process signal** — was the agent's approach efficient? Did the dev provide good context? Were there unnecessary retries or false completions?
3. **Repo signal** — what characteristics of the repository slowed the agent down? Missing types, unclear naming, no test harness?

Reviewers currently open a PR and see only the diff. They have no window into how the code was produced, whether the agent struggled, or whether the dev's prompting was effective.

## Solution

A Claude Code plugin distributed as a git submodule that generates a self-contained eval pack — a polished static HTML report capturing the full story of how code was produced. The eval pack deploys to GitHub Pages via a bundled GitHub Action and is linked directly from the PR comment.

## Distribution Model

Git submodule at `.claude/plugins/eval-pack/`. Target repo's `.claude/settings.json` references the plugin:

```json
{
  "plugins": [".claude/plugins/eval-pack"],
  "pluginConfigs": {
    "eval-pack": {
      "options": {
        "outputDir": ".eval-packs",
        "includeTranscript": true,
        "redactPatterns": ["\\.env", "SECRET", "TOKEN"],
        "analysis": true,
        "pagesBaseUrl": "https://<org>.github.io/<repo>/eval-packs"
      }
    }
  }
}
```

Devs clone the repo, run `git submodule update --init`, and the plugin is active. Updates are rolled out by bumping the submodule ref.

## Plugin Structure

```
eval-pack/
├── .claude-plugin/
│   └── plugin.json
├── skills/
│   ├── generate/
│   │   └── SKILL.md            # Core: analyze transcript, run tests, produce eval pack
│   ├── setup/
│   │   └── SKILL.md            # One-time: copy action + config into target repo
│   └── review/
│       └── SKILL.md            # Generate pack + create/update PR + post comment
├── templates/
│   ├── workflows/
│   │   └── eval-pack-pages.yml # GitHub Action template
│   └── html/
│       ├── index.html          # Eval pack HTML shell
│       ├── styles.css
│       └── scripts.js
├── scripts/
│   ├── extract-metrics.sh      # Parse transcript JSONL → metrics.json
│   ├── detect-patterns.sh      # Heuristic flags → patterns.json
│   └── render-html.sh          # Inject data into HTML template
└── settings.json               # Default plugin config
```

No hooks. Generation is triggered by skill invocation — dev or agent decides when.

## Skills

### `/eval-pack:generate`

The core skill. Invoked manually by dev or autonomously by agent when it judges work is PR-ready.

Execution flow:

1. **Extract metrics** — runs `extract-metrics.sh`. Parses transcript JSONL and git diff. Produces `metrics.json` containing: model, total tokens, turn count, duration, files changed, lines added/removed.
2. **Detect patterns** — runs `detect-patterns.sh`. Analyzes transcript for: false completions (agent claimed done but wasn't), high retry counts, scope drift (files changed outside expected area), test failures during session. Produces `patterns.json`.
3. **Run tests** — Claude identifies appropriate tests for the changes made. Runs unit tests, integration tests, Playwright e2e tests, or opens a browser to visually verify — whatever is appropriate. Captures screenshots, logs, and pass/fail results.
4. **Analyze transcript** — Claude reads its own transcript plus metrics and patterns. Writes three analysis sections:
   - **Retrospective** — what went well, what was slow, where time was wasted
   - **Repo Friction** — what repository characteristics slowed things down
   - **Prompt Quality** — was initial context sufficient, what would have helped
5. **Determine round** — checks if pack already exists for this session. If regenerating after feedback, appends new round data rather than overwriting. Timeline shows iteration rounds.
6. **Render HTML** — runs `render-html.sh`. Injects all JSON data, transcript, screenshots, and logs into HTML template. Produces final self-contained eval pack.

Output directory structure:

```
.eval-packs/<session-id>/
├── index.html
├── styles.css
├── scripts.js
├── data.json
├── transcript.jsonl
├── metrics.json
├── patterns.json
├── analysis.json
├── screenshots/
│   ├── before-change.png
│   ├── after-change.png
│   └── test-result.png
└── logs/
    ├── test-output.log
    └── build-output.log
```

### `/eval-pack:review`

Wraps generate with PR workflow:

1. Calls `generate` internally
2. Creates PR via `gh pr create` or updates existing PR
3. Commits `.eval-packs/` to PR branch
4. Posts summary comment with verdict badge and link to Pages URL

### `/eval-pack:setup`

One-time repo bootstrap:

1. Copies `eval-pack-pages.yml` into `.github/workflows/`
2. Adds default config to `.claude/settings.json`
3. Adds `.eval-packs/` to main branch `.gitignore` (packs live on PR branches only)
4. Enables GitHub Pages on `gh-pages` branch if `gh` CLI available
5. Adds eval-pack submodule to `.claude/plugins/`

## Eval Pack HTML Contents

Seven sections, ordered by reviewer scan pattern — high-level first, drill-down below:

### 1. Verdict Banner

Pass/fail badge at top of page. Determined by test results from agent-driven testing. Red = any test failed. Green = all tests passed. Amber = no tests ran.

### 2. Screenshots / Visual Evidence

Inline expandable screenshots from Playwright or browser verification. Reviewer sees what the change looks like visually before reading any metrics.

### 3. Stats Card

Single row of key metrics: model, total tokens, turn count, session duration, files changed count, lines added/removed.

### 4. Phase Timeline

Visual bar showing phases: Understanding → Planning → Implementation → Testing → Fixing. Width proportional to tokens spent per phase. False completion loops highlighted in amber. Iteration rounds (from regeneration after feedback) marked as distinct sections in the timeline.

### 5. Heuristic Flags

Automated pattern detection shown as colored chips:

- Red: test failures during session
- Amber: false completions (agent said done, wasn't)
- Amber: high retry count
- Amber: scope drift (files changed outside expected area)
- Green: clean first-pass implementation

### 6. Claude Analysis

Three subsections generated by Claude:

- **Retrospective** — what went well, what was slow, where time was wasted
- **Repo Friction** — what repo characteristics slowed things down (missing types, unclear structure, no test harness)
- **Prompt Quality** — was initial context sufficient, what front-loaded context would have helped

### 7. Full Transcript

Collapsible. Syntax-highlighted code blocks. Each turn labeled with role and timestamp.

## Visual Style

Polished, dashboard-like. Cards, color-coded status badges, collapsible sections, light/dark toggle. Similar to Vercel deployment summary aesthetic.

## Data Flow

```
Skill invocation
    │
    ▼
extract-metrics.sh ──→ metrics.json
    │                   (tokens, turns, model, duration, files changed)
    ▼
detect-patterns.sh ──→ patterns.json
    │                   (false completions, retries, scope drift, failures)
    ▼
Claude (generate skill)
    │  reads: transcript, metrics.json, patterns.json
    │  runs: appropriate tests, captures screenshots/logs
    │  writes: analysis.json (retrospective, friction, prompt quality)
    │
    ▼
render-html.sh ──→ .eval-packs/<session-id>/
    │               (index.html, styles.css, scripts.js, data.json,
    │                transcript.jsonl, screenshots/, logs/)
    ▼
(if /eval-pack:review)
    │
    ▼
gh pr create + comment with verdict badge + Pages link
    │
    ▼
GitHub Action deploys HTML to gh-pages branch
```

Key properties:
- Scripts produce intermediate JSON files — each stage independently testable
- `data.json` bundled with HTML for client-side rendering (JS reads it, no server)
- Transcript copied into pack dir — self-contained artifact
- Test evidence (screenshots, logs) stored alongside HTML

## Configuration

Via `.claude/settings.json` in target repo:

| Option | Type | Default | Purpose |
|--------|------|---------|---------|
| `outputDir` | string | `.eval-packs` | Where packs land |
| `includeTranscript` | bool | `true` | Full chat in pack |
| `redactPatterns` | string[] | `[]` | Regex patterns stripped from transcript before inclusion |
| `analysis` | bool | `true` | Claude retrospective on/off. False = heuristics only |
| `pagesBaseUrl` | string | `null` | Base URL for PR comment links to deployed eval packs |

No `testCommand` or `lintCommand` — agent determines appropriate testing based on changes made.

## GitHub Action Template

Bundled at `templates/workflows/eval-pack-pages.yml`. Copied into target repo by `/eval-pack:setup`.

Triggers on PR open/synchronize when `.eval-packs/` has changes. Steps:

1. Find eval packs in `.eval-packs/`
2. Deploy HTML to `gh-pages` branch under `eval-packs/<session-id>/`
3. Post PR comment with verdict badge and link to rendered eval pack

`gh-pages` branch is independent — never merges into main. Accumulates packs over time.

## Regeneration

When dev receives PR feedback and makes fixes:

1. Dev fixes in same session
2. Runs `/eval-pack:generate` again
3. Skill detects existing pack for session — appends new round data
4. Timeline shows iteration: original work → feedback → fixes
5. Push to PR branch → Action redeploys → comment updates

Single pack, multiple rounds. Reviewer sees full story in one view.

Data model: `data.json` contains a `rounds` array. Each round captures its own `metrics`, `patterns`, `analysis`, and `testResults` snapshot. The HTML timeline renders each round as a distinct section. Round 1 is the original work; subsequent rounds capture post-feedback iterations.

## Gitignore Strategy

`.eval-packs/` added to `.gitignore` on main branch. Packs are committed to PR branches only. On merge, pack artifacts don't enter main. GitHub Action has already deployed them to `gh-pages` for permanent access.

## Non-Goals

- Cross-session dashboard or analytics (individual packs only)
- Token cost tracking or billing integration
- Plugin marketplace distribution (submodule only)
- Automated hook-based triggering (manual/agent skill invocation only)
