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
