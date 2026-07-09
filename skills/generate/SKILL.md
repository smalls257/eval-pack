---
description: Generate an eval pack — a polished HTML report capturing conversation history, metrics, heuristic patterns, test results, and AI analysis. Run this when work is PR-ready.
tags: ["eval", "review", "metrics"]
---

# Generate Eval Pack

## Prerequisites

Resolve the Python command from plugin config (the `pythonExecutable` userConfig, exposed as the
env var `CLAUDE_PLUGIN_OPTION_pythonExecutable`; default `python3`), then verify it runs. Use this
`$PYTHON` for every script invocation below — Windows users can set it to `python` or `py`.

```bash
PYTHON="${CLAUDE_PLUGIN_OPTION_pythonExecutable:-python3}"
"$PYTHON" --version
```

If this fails, stop and tell the user: `"Error: Python 3 is required by eval-pack. Install from python.org, then either ensure 'python3' is on PATH or set the plugin's pythonExecutable config (e.g. 'python' or 'py' on Windows)."`

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
  | "$PYTHON" -c "import sys,json; lines=[l for l in sys.stdin.read().splitlines() if l.strip()]; print(json.dumps(lines))" \
  || echo "[]")
```

If git is unavailable, all variables default to empty/zero — scripts proceed with blank git stats.

## Step 0.6: Assemble the Whole Conversation

Evaluate the **whole** unit of work. Only the current session is included automatically;
every prior session is **opt-in and prompted** — branch only decides what is pre-suggested.

List relevance-tagged candidates (archived + discovered, deduped, current excluded):

```bash
"$PYTHON" "${CLAUDE_PLUGIN_ROOT}/scripts/list_candidates.py" "$(pwd)" "${SESSION_ID}" "${BRANCH}"
```

This prints a JSON array; each item has `sessionId`, `transcriptPath`, `source`
(`archive`/`discovered`), `branches`, `firstPrompt`, `timeRange`, `msgCount`, and `relevant`
(true when its branches include the current branch `${BRANCH}`).

- **Interactive run (default for `/eval-pack:generate` and `/eval-pack:review`):** if the array is
  non-empty, present the candidates as a checklist — **pre-check the `relevant: true`** ones (same
  branch) and leave the rest unchecked. Show first prompt + branch + time range + message count per
  item. Ask the user to confirm or edit. The user MAY pick none. Collect the `transcriptPath` of
  each confirmed item into repeated `--select` flags below.
- **Non-interactive run (CI / headless):** do NOT prompt and pass NO `--select` flags — evaluate the
  current session only. State that coverage is current-session-only.
- **Honest coverage (Sensor):** if the list is empty, say "no prior sessions found"; never imply the
  conversation is provably complete (a session outside this repo's dirs cannot be discovered).

Assemble the merged transcript (current + confirmed selections + their sub-agent transcripts):

Write it to `${PACK_DIR}/transcript.jsonl` — the canonical name every later step reads (extraction,
the Step 4 evaluator, and Step 5 render):

```bash
mkdir -p "${PACK_DIR}"
"$PYTHON" "${CLAUDE_PLUGIN_ROOT}/scripts/build_conversation.py" "${TRANSCRIPT_PATH}" "${SESSION_ID}" "${PACK_DIR}/transcript.jsonl" \
  --select "<transcriptPath of each confirmed candidate>"   # repeat --select per candidate; omit if none
```

If `${PACK_DIR}/transcript.jsonl` was written (`1` or more sessions), set
`TRANSCRIPT_PATH="${PACK_DIR}/transcript.jsonl"` and use it for every remaining step (Steps 1, 2,
2.5, the Step 4 analysis input, and Step 5 render) — this guarantees the evaluator has a transcript
to read. Otherwise keep the original `TRANSCRIPT_PATH`.

## Step 0.7: Resolve Configuration

Resolve the layered eval-pack config into the pack directory. This validates
`.eval-pack.json` (and any `.eval-pack.local.json` / `extends` presets) and writes the single
`eval-config.json` that every downstream step reads. If it exits non-zero, STOP and show the user
the stderr verbatim — a config error must halt the run, not silently fall back to defaults.

```bash
"$PYTHON" "${CLAUDE_PLUGIN_ROOT}/scripts/resolve_config.py" "$(pwd)" "${PACK_DIR}"
```

## Step 1: Extract Metrics

Run the extract-metrics script against the current session transcript:

```bash
"$PYTHON" "${CLAUDE_PLUGIN_ROOT}/scripts/extract_metrics.py" "${TRANSCRIPT_PATH}" "${PACK_DIR}" \
  --insertions "${INSERTIONS}" \
  --deletions "${DELETIONS}" \
  --files-changed "${FILES_CHANGED}" \
  --changed-files "${CHANGED_FILES}" \
  --config "${PACK_DIR}/eval-config.json"
```

Where:
- `TRANSCRIPT_PATH` is the transcript file for this session
- `PACK_DIR` is `<outputDir>/<session-id>` (outputDir from plugin config, default `.eval-packs`; session-id from current session)

If the transcript path is not available, read the conversation history from context and write it to `${PACK_DIR}/transcript.jsonl` in JSONL format with fields: `type` (human/assistant), `timestamp`, `content`, and for assistant turns: `model`, `usage.input_tokens`, `usage.output_tokens`.

## Step 2: Detect Patterns

Run the detect-patterns script:

```bash
"$PYTHON" "${CLAUDE_PLUGIN_ROOT}/scripts/detect_patterns.py" "${TRANSCRIPT_PATH}" "${PACK_DIR}" --config "${PACK_DIR}/eval-config.json"
```

## Step 2.5: Extract Tool Usage

Run the extract-tools script:

```bash
"$PYTHON" "${CLAUDE_PLUGIN_ROOT}/scripts/extract_tools.py" "${TRANSCRIPT_PATH}" "${PACK_DIR}" --config "${PACK_DIR}/eval-config.json"
```

If the transcript path is not available or the script fails, continue — `render_html.py` will fall back to `{}` automatically.

## Step 3: Run Tests

First read `testCommands` from `${PACK_DIR}/eval-config.json`. **If it is non-empty, run EXACTLY
those commands** (in order, from the repo root), capture each command's real exit code and output,
and base the test verdict on those real exit codes — do not guess at runners. Only when
`testCommands` is empty fall back to the detection heuristics below:

When `testCommands` ran, `test-results.json` MUST record the proof — one entry per configured
command, verbatim, with its real exit code — and the verdict MUST follow the exit codes
(all zero → `pass`, any nonzero → `fail`). A validator enforces this mechanically:

```json
{
  "verdict": "fail",
  "summary": "1 of 2 configured commands failed",
  "commands": [
    {"command": "<verbatim from testCommands>", "exitCode": 0},
    {"command": "<verbatim from testCommands>", "exitCode": 1}
  ],
  "testsRun": [ {"name": "…", "passed": false, "output": "…"} ]
}
```

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
   - For any screenshot produced by an **automated test run** (not the agent driving the
     browser), record its provenance so the report does not have to guess: append an entry
     to `${PACK_DIR}/screenshots/sources.json` mapping the filename to `"test"`, e.g.
     `{"login-flow.png": "test"}`. Screenshots the agent captured via `browser_take_screenshot`
     are detected automatically from the transcript and need no entry. Anything unrecorded
     renders as "Unknown source".
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
                   # Branch-scoped: carry prior-round screenshots regardless of
                   # session id (mirrors render_html.load_prior_rounds, which no
                   # longer gates on sessionId across resumed sessions).
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
> Read eval-config.json (your configuration), transcript.jsonl, metrics.json, patterns.json,
> and test-results.json from PACK_DIR,
> run git from REPO_ROOT to inspect the diff against DIFF_BASE, and write
> `${ABS_PACK_DIR}/analysis.json` per your schema.

Wait for the agent to finish. Confirm `${ABS_PACK_DIR}/analysis.json` exists and has a
`title`. If it is missing or empty, the evaluator failed — re-dispatch once; if it
fails again, stop and tell the user the analysis step failed. Do NOT write the
analysis yourself as a fallback — that reintroduces the bias this step exists to remove.

Then run the deterministic contract gate — it checks the analysis and test results against the
resolved config (friction taxonomy, retrospective answers, rubric band, test-command proof):

```bash
"$PYTHON" "${CLAUDE_PLUGIN_ROOT}/scripts/validate_contracts.py" "${ABS_PACK_DIR}"
```

If it exits non-zero, route each `CONTRACT:` line to its owner:
- **Analysis violations** (frictionLog / retrospectiveAnswers / rubricApplied): re-dispatch the
  evaluator ONCE, passing those lines as corrections.
- **Test violations** (test-results.commands / verdict): the evaluator cannot fix these — redo
  Step 3 so `test-results.json` records every configured command with its real exit code and a
  verdict consistent with them.
Re-run the gate. If it still fails, STOP and show the user the violations — do not render.
(render_html enforces the same gate; skipping this step cannot ship a non-conforming pack.)

**If analysis is disabled** (`analysis` option is false):

Do not dispatch the evaluator. Write a minimal, honest stub so the dashboard shows a
clear "analysis disabled" banner rather than a fabricated score:

```bash
"$PYTHON" - "${PACK_DIR}" << 'PY'
import json, sys, pathlib
pack = pathlib.Path(sys.argv[1])
pack.mkdir(parents=True, exist_ok=True)
(pack / "analysis.json").write_text(json.dumps({
    "title": "Analysis disabled — heuristic flags only",
    "disabled": True,
}), encoding="utf-8")
PY
```

## Step 4.7: Extension Lenses (optional)

Read `analysisLenses` from `${PACK_DIR}/eval-config.json`. If it is empty, SKIP this entire
step — the core eval never depends on a lens being present (the Airplane Test). The
configuration was validated at resolve time, so every lens already has a `skill` and a valid
`role`.

Create the lens output dir: `mkdir -p "${PACK_DIR}/lenses"`. Then for each lens `{skill, role}`,
dispatch it as a SEPARATE subagent over the read-only artifacts. Each lens WRITES its result to
`${PACK_DIR}/lenses/<id>.json` (the assembler collects these). Pass only artifact locations —
never your own reasoning.

**First-party lenses** ship with eval-pack; dispatch each with the `Agent` tool using the matching
`subagent_type`, passing `PACK_DIR` (absolute), `REPO_ROOT`, and `DIFF_BASE`:

- `requirement-drift` (scorer) — did the delivered work match what the user originally asked?
- `verification-rigor` (scorer) — were success claims backed by observed evidence?

> Run the `<skill>` lens. PACK_DIR is `${ABS_PACK_DIR}`. REPO_ROOT is `${REPO_ROOT}`. DIFF_BASE is
> `${DIFF_BASE}`. Read the artifacts, then write your result to
> `${ABS_PACK_DIR}/lenses/<skill>.json` per your schema.

A **third-party** lens is dispatched as its named skill/agent; instruct it to write the same
`{skill, role, score|title, rationale|findings}` shape to `lenses/<skill>.json`. A `contributor`
adds an attributed section and MUST NOT touch the verdict; a `scorer` returns a 0–100 `score` that
reaches the verdict only through the declared `verdictAggregation` rule. If a lens errors or writes
malformed output, leave a note in `lenses/<skill>.json` — the assembler quarantines it as a
failure and the eval continues (never crashes, never silently vanishes).

Then assemble the results and compute the aggregated verdict with the tested script (the math is
not done by hand — that keeps the verdict auditable):

```bash
"$PYTHON" "${CLAUDE_PLUGIN_ROOT}/scripts/assemble_lenses.py" "${PACK_DIR}"
```

This writes `${PACK_DIR}/lenses.json` — contributors, scorers, failures, `coreScore`, and the
aggregated `finalScore` — which the report's Lenses tab renders.

Guards: rules come from config set before the run sees results (G1, pre-committed); every result is
attributed and the aggregation math is written to lenses.json (G2, transparent); the rule was
bounded to a known, can-still-fail rule at resolve time (G3); lenses are config-listed only,
failures degrade to quarantined notes, and the core ran without them (G4, isolated).

## Step 5: Render HTML

Run the render script:

```bash
"$PYTHON" "${CLAUDE_PLUGIN_ROOT}/scripts/render_html.py" "${OUTPUT_DIR}" "${SESSION_ID}" "${CLAUDE_PLUGIN_ROOT}" "${TRANSCRIPT_PATH}" \
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
