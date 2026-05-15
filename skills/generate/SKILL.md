---
description: Generate an eval pack — a polished HTML report capturing conversation history, metrics, heuristic patterns, test results, and AI analysis. Run this when work is PR-ready.
tags: ["eval", "review", "metrics"]
---

# Generate Eval Pack

## Prerequisites

Verify Python 3 is available before running any scripts:

```bash
python3 --version
```

If this fails, stop and tell the user: `"Error: Python 3 is required by eval-pack. Install from python.org and ensure python3 is in your PATH."`

You are generating an eval pack for the current session. Follow these steps in order.

## Step 1: Extract Metrics

Run the extract-metrics script against the current session transcript:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/extract_metrics.py" "${TRANSCRIPT_PATH}" "${PACK_DIR}"
```

Where:
- `TRANSCRIPT_PATH` is the transcript file for this session
- `PACK_DIR` is `<outputDir>/<session-id>` (outputDir from plugin config, default `.eval-packs`; session-id from current session)

If the transcript path is not available, read the conversation history from context and write it to `${PACK_DIR}/transcript.jsonl` in JSONL format with fields: `type` (human/assistant), `timestamp`, `content`, and for assistant turns: `model`, `usage.input_tokens`, `usage.output_tokens`.

## Step 2: Detect Patterns

Run the detect-patterns script:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/detect_patterns.py" "${TRANSCRIPT_PATH}" "${PACK_DIR}"
```

## Step 2.5: Extract Tool Usage

Run the extract-tools script:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/extract_tools.py" "${TRANSCRIPT_PATH}" "${PACK_DIR}"
```

If the transcript path is not available or the script fails, continue — `render_html.py` will fall back to `{}` automatically.

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
4. Sweep for additional screenshots from the session:

   Run this Python snippet to find screenshots in `.playwright-mcp/` that fall within the session window (using `firstTimestamp`/`lastTimestamp` from `${PACK_DIR}/metrics.json`):

   ```python
   import json, pathlib, datetime, os
   metrics = json.loads(pathlib.Path("${PACK_DIR}/metrics.json").read_text())
   start = datetime.datetime.fromisoformat(metrics.get("firstTimestamp","").replace("Z","+00:00")) if metrics.get("firstTimestamp") else None
   end   = datetime.datetime.fromisoformat(metrics.get("lastTimestamp","").replace("Z","+00:00"))  if metrics.get("lastTimestamp")  else None
   candidates = []
   already = {p.name for p in pathlib.Path("${PACK_DIR}/screenshots").glob("*.png")}
   for png in sorted(pathlib.Path(".playwright-mcp").glob("*.png")):
       if png.name in already: continue
       mtime = datetime.datetime.fromtimestamp(png.stat().st_mtime, tz=datetime.timezone.utc)
       if start and mtime < start: continue
       if end   and mtime > end:   continue
       candidates.append(png)
   for c in candidates:
       print(c.name)
   ```

   If candidates are found, show the list to the user and ask: **"These screenshots from `.playwright-mcp/` fall within the session window. Include any in the eval pack?"** Copy confirmed ones to `${PACK_DIR}/screenshots/`.

   If no candidates, continue.

5. Write test results to `${PACK_DIR}/test-results.json`:

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

If enabled, read the transcript, metrics.json, and patterns.json. Write `${PACK_DIR}/analysis.json` with this schema:

```json
{
  "title": "Short task description for page heading (1 sentence, no period)",
  "highlights": {
    "completionStatus": { "label": "Completion below", "color": "green", "notes": "One sentence on what was achieved" },
    "confidencePercent": 85,
    "confidenceNotes": "One sentence explaining the confidence score — what evidence supports it or limits it",
    "businessRisk": { "level": "low|medium|high", "notes": "One sentence on why this risk level was assigned" },
    "riskMitigation": ["Step to reduce risk", "Step to reduce risk"],
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
  "reviewFindings": [
    {"issue": "Short description of what the reviewer found", "severity": "critical|important|suggestion", "foundIn": "Task N — filename.py or section name", "resolution": "How it was fixed", "commit": "commit message or short SHA (optional)"}
  ],
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
  "sessionTimeline": [
    "User asked to X — brief neutral description of the opening prompt",
    "Agent and user brainstormed Y — key decisions made",
    "Agent implemented Z using subagents",
    "Code review caught issues, fixes applied",
    "Session concluded with outcome"
  ],
  "sessionArtifacts": [
    {"name": "artifact name", "path": "relative/path/in/pack", "description": "what this artifact contains"}
  ],
  "verdictStatement": "Closing italic sentence summarizing the session outcome and its trustworthiness as evidence."
}
```

Be specific and actionable. Reference actual files, patterns, and moments from the transcript. Do not include empty arrays or null fields — omit sections for which there is no data.

## Step 5: Render HTML

Run the render script:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/render_html.py" "${OUTPUT_DIR}" "${SESSION_ID}" "${CLAUDE_PLUGIN_ROOT}" "${TRANSCRIPT_PATH}"
```

This assembles the final eval pack with all data, handles round detection for regeneration, and copies template files.

## Step 6: Report

Tell the user:
- Where the eval pack was written
- The verdict (pass/fail/none)
- Key flags detected
- That they can open `index.html` in a browser to view the full report
- That they can run `/eval-pack:review` to create a PR with the eval pack attached
