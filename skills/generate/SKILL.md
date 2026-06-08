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

## Step 0: Gather Git Context

Run these commands to collect git metadata. Store results as shell variables — pass them as arguments to extraction scripts.

```bash
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
if git rev-parse HEAD~1 >/dev/null 2>&1; then
    DIFF_BASE="HEAD~1"
else
    DIFF_BASE="4b825dc642cb6eb9a060e54bf8d69288fbee4904"
fi
DIFF_STAT=$(git diff --stat "$DIFF_BASE" 2>/dev/null || echo "")
INSERTIONS=$(echo "$DIFF_STAT" | grep -oE '[0-9]+ insertion' | grep -oE '[0-9]+' || echo "0")
DELETIONS=$(echo "$DIFF_STAT" | grep -oE '[0-9]+ deletion' | grep -oE '[0-9]+' || echo "0")
FILES_CHANGED=$(git diff --name-only "$DIFF_BASE" 2>/dev/null | wc -l | tr -d ' ' || echo "0")
CHANGED_FILES=$(git diff --name-only "$DIFF_BASE" 2>/dev/null \
  | python3 -c "import sys,json; lines=[l for l in sys.stdin.read().splitlines() if l.strip()]; print(json.dumps(lines))" \
  || echo "[]")
```

If git is unavailable, all variables default to empty/zero — scripts proceed with blank git stats.

## Step 1: Extract Metrics

Run the extract-metrics script against the current session transcript:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/extract_metrics.py" "${TRANSCRIPT_PATH}" "${PACK_DIR}" \
  --insertions "${INSERTIONS}" \
  --deletions "${DELETIONS}" \
  --files-changed "${FILES_CHANGED}" \
  --changed-files "${CHANGED_FILES}"
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
   import json, pathlib, datetime, zipfile, re
   metrics = json.loads(pathlib.Path("${PACK_DIR}/metrics.json").read_text())
   start = datetime.datetime.fromisoformat(metrics.get("firstTimestamp","").replace("Z","+00:00")) if metrics.get("firstTimestamp") else None
   end   = datetime.datetime.fromisoformat(metrics.get("lastTimestamp","").replace("Z","+00:00"))  if metrics.get("lastTimestamp")  else None

   # names already in pack_dir or in any previous round in the zip
   already = {p.name for p in pathlib.Path("${PACK_DIR}/screenshots").glob("*.png")}
   zip_path = pathlib.Path("${OUTPUT_DIR}/${ZIP_NAME}.zip")
   if zip_path.is_file():
       with zipfile.ZipFile(zip_path) as z:
           for name in z.namelist():
               if name.endswith("data.json"):
                   prev = json.loads(z.read(name))
                   if prev.get("sessionId") == "${SESSION_ID}":
                       for r in prev.get("rounds", []):
                           for s in r.get("screenshots", []):
                               already.add(pathlib.Path(s.get("path","")).name)
                   break

   candidates = []
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

## Step 4: Analyze (independent evaluator)

The analysis must NOT be written by you — you did the work, and a self-graded
evaluation is not trustworthy evidence. Dispatch an independent evaluator instead.

First compute the diff base (same logic as Step 0):

- If `HEAD~1` exists, `DIFF_BASE=HEAD~1`; otherwise `DIFF_BASE=4b825dc642cb6eb9a060e54bf8d69288fbee4904` (empty tree).

**If analysis is enabled** (plugin config `analysis` option, default true):

Resolve `PACK_DIR` to an absolute path and capture the repo root before dispatching, so
the sub-agent (which may run from a different working directory) resolves files and git
correctly:

- `ABS_PACK_DIR=$(cd "${PACK_DIR}" && pwd)`
- `REPO_ROOT=$(git rev-parse --show-toplevel)`

Dispatch the `eval-pack-evaluator` agent with the `Agent` tool, `subagent_type:
eval-pack-evaluator`. Pass it only the artifact location — not your own reasoning:

> Write the eval-pack analysis. PACK_DIR is `${ABS_PACK_DIR}` (absolute). REPO_ROOT is
> `${REPO_ROOT}`. DIFF_BASE is `${DIFF_BASE}`.
> Read transcript.jsonl, metrics.json, patterns.json, and test-results.json from PACK_DIR,
> run git from REPO_ROOT to inspect the diff against DIFF_BASE, and write
> `${ABS_PACK_DIR}/analysis.json` per your schema.

Wait for the agent to finish. Confirm `${ABS_PACK_DIR}/analysis.json` exists and has a
`title`. If it is missing or empty, the evaluator failed — re-dispatch once; if it
fails again, stop and tell the user the analysis step failed. Do NOT write the
analysis yourself as a fallback — that reintroduces the bias this step exists to remove.

**If analysis is disabled** (`analysis` option is false):

Do not dispatch the evaluator. Write a minimal, honest stub so the dashboard shows a
clear "analysis disabled" banner rather than a fabricated score:

```bash
python3 - "${PACK_DIR}" << 'PY'
import json, sys, pathlib
pack = pathlib.Path(sys.argv[1])
pack.mkdir(parents=True, exist_ok=True)
(pack / "analysis.json").write_text(json.dumps({
    "title": "Analysis disabled — heuristic flags only",
    "disabled": True,
}), encoding="utf-8")
PY
```

## Step 5: Render HTML

Run the render script:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/render_html.py" "${OUTPUT_DIR}" "${SESSION_ID}" "${CLAUDE_PLUGIN_ROOT}" "${TRANSCRIPT_PATH}" \
  --branch "${BRANCH}"
```

This assembles the final eval pack with all data, handles round detection for regeneration, and copies template files.

## Step 6: Report

Tell the user:
- Where the eval pack was written
- The verdict (pass/fail/none)
- Key flags detected
- The `Open: file://…/index.html` path that `render_html.py` printed — they can open it directly in a browser, no unzip needed
- That the committed zip in `<outputDir>/` is the portable copy for PRs
- That they can run `/eval-pack:review` to create a PR with the eval pack attached
