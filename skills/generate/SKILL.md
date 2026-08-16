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
the lenses, the Step 4.5 evaluator, and Step 5 render):

```bash
mkdir -p "${PACK_DIR}"
"$PYTHON" "${CLAUDE_PLUGIN_ROOT}/scripts/build_conversation.py" "${TRANSCRIPT_PATH}" "${SESSION_ID}" "${PACK_DIR}/transcript.jsonl" \
  --select "<transcriptPath of each confirmed candidate>"   # repeat --select per candidate; omit if none
```

If `${PACK_DIR}/transcript.jsonl` was written (`1` or more sessions), set
`TRANSCRIPT_PATH="${PACK_DIR}/transcript.jsonl"` and use it for every remaining step (Steps 1, 2,
2.5, the lens dispatches, the Step 4.5 analysis input, and Step 5 render) — this guarantees the
evaluator has a transcript to read. Otherwise keep the original `TRANSCRIPT_PATH`.

## Step 0.65: Discover Repos Touched (multi-repo coverage)

Today's diff step (Step 0 / Step 4.5) only diffs the cwd's repo. If a sub-agent did real work in a
different repo or worktree during this session, that change surface is invisible and the eval
scores a partial diff without saying so. This step restores that visibility. This step is also
ENFORCED deterministically: render re-derives which repos the session edited (via
Edit/Write/MultiEdit/NotebookEdit) from the transcript and REFUSES to render if ≥2 such repos
aren't all accounted. Limitation: a second repo modified ONLY through Bash file writes (e.g.
`cat >`, `sed -i`, `git commit` — not the edit tools) has no write signal and is not detected —
prefer the edit tools, or explicitly cover such repos in the selection.

Run the discovery script against the assembled transcript and save its stdout — a JSON array —
verbatim:

```bash
"$PYTHON" "${CLAUDE_PLUGIN_ROOT}/scripts/discover_repos.py" "${PACK_DIR}/transcript.jsonl" \
  > "${PACK_DIR}/discovered-repos.json"
```

Partition the discovered repos:

- **Auto-skip obvious non-project repos** — any `repoRoot` under `~/.claude/plugins`,
  `site-packages`, `/tmp`, or another dependency/cache directory. These are tooling the session
  incidentally touched, not session work; record them as `{"repoRoot": ..., "skip": true}` with
  reason `"tooling/library, not session work"`. Do NOT prompt the user about these.
- **Remaining project repos:**
  - If there is exactly **one**, and it is the cwd repo, auto-select it with
    `base = ${DIFF_BASE}` (the Step 0 value) — no prompt, same behavior as before this step
    existed.
  - If there is **more than one**, this is the multi-repo case — **stop and ask the user**. We do
    NOT guess a base; the user chooses, every time. For each such repo, present its `repoRoot`,
    `branch`, `touchCount`, and `signals`, then offer candidate bases:
    - Run `git -C <repoRoot> branch --format='%(refname:short)'` and list the branches.
    - Also offer "the empty-tree sha (everything new)" — `4b825dc642cb6eb9a060e54bf8d69288fbee4904`.
    - Also offer "type a specific commit SHA".
    - Also offer "skip this repo".

    Collect the user's choice per repo.

Write every discovered repo's disposition — auto-skipped, auto-selected, and user-chosen — to
`${PACK_DIR}/repo-selection.json`. When writing it, copy each `repoRoot` BYTE-FOR-BYTE from
discovered-repos.json — do not retype, expand, or add a trailing slash. (The coverage gate
canonicalizes paths, but a verbatim copy avoids any ambiguity.)

```json
{"repos": [
  {"repoRoot": "/path/to/repo", "base": "main"},
  {"repoRoot": "/path/to/other-repo", "skip": true}
]}
```

Then compute the diffs:

```bash
"$PYTHON" "${CLAUDE_PLUGIN_ROOT}/scripts/repo_diffs.py" "${PACK_DIR}" \
  --selection "${PACK_DIR}/repo-selection.json"
```

This writes `${PACK_DIR}/repo-diffs.json`. Coverage backstop: render refuses if a discovered repo
is left neither diffed nor skipped (Step 4.5's contract gate and render both enforce it), so
account for every one — don't leave a repo out of `repo-selection.json`.

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
- `PACK_DIR` is `<outputDir>/<session-id>` (`outputDir` from the resolved `eval-config.json`, default `.eval-packs` — legacy plugin option still works via the env layer; session-id from current session)

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

## Step 4: Extension Lenses (optional)

The evaluator (Step 4.5) is a synthesizer — it reads lens findings rather than re-deriving them.
That only works if the lenses have already run, so this step comes BEFORE the evaluator dispatch.

Read `analysisLenses` from `${PACK_DIR}/eval-config.json`. If it is empty, SKIP this entire
step — the core eval never depends on a lens being present (the Airplane Test). The
configuration was validated at resolve time, so every lens already has a `skill` and a valid
`role`.

Resolve `PACK_DIR` to an absolute path and capture the repo root before dispatching, so
sub-agents (which may run from a different working directory) resolve files and git correctly.
Compute the diff base the same way as Step 0:

- `ABS_PACK_DIR=$(cd "${PACK_DIR}" && pwd)`
- `REPO_ROOT=$(git rev-parse --show-toplevel)`
- If `HEAD~1` exists, `DIFF_BASE=HEAD~1`; otherwise `DIFF_BASE=4b825dc642cb6eb9a060e54bf8d69288fbee4904` (empty tree).

Create the lens output dir: `mkdir -p "${PACK_DIR}/lenses"`.

**Build the transcript views (cost lever).** Compute the set of views the enabled lenses declare
(each lens's frontmatter `inputs.transcript`, default `full`) and materialize only those, once:

    VIEWS=$("$PYTHON" "${CLAUDE_PLUGIN_ROOT}/scripts/lens_inputs.py" \
        "${CLAUDE_PLUGIN_ROOT}/agents/lenses" "${PACK_DIR}/eval-config.json")
    # VIEWS is a space-separated set excluding "full"; if empty, skip view building (no-op).
    # $VIEWS is intentionally left unquoted below — it must word-split into separate
    # positional args for build_views.py; quoting it would pass one empty/combined arg instead.
    if [ -n "$VIEWS" ]; then
        "$PYTHON" "${CLAUDE_PLUGIN_ROOT}/scripts/build_views.py" \
            "${PACK_DIR}/transcript.jsonl" "${PACK_DIR}/views" $VIEWS \
            --tool-result-trunc-len "$(jq -r '.toolResultTruncLen // 400' "${PACK_DIR}/eval-config.json")"
    fi

For each lens, resolve its TRANSCRIPT path: if the lens declares `full` (or declares nothing),
TRANSCRIPT = `${ABS_PACK_DIR}/transcript.jsonl`; otherwise TRANSCRIPT =
`${ABS_PACK_DIR}/views/<view>.jsonl`. If the lens's declared view is `skeleton`, also pass
RAW_TRANSCRIPT = `${ABS_PACK_DIR}/transcript.jsonl` — the pull source. For non-skeleton lenses,
omit it.

Then for each lens `{skill, role, model?}`, dispatch it as a SEPARATE subagent over the read-only
artifacts. Each lens WRITES its result to `${PACK_DIR}/lenses/<id>.json` (the assembler collects
these). Pass only artifact locations — never your own reasoning.

**Per-lens model (cost/quality tuning):** if a lens entry has a `model` (`opus`|`sonnet`|`haiku`|
`fable`), pass it as the `Agent` tool's `model` argument for THAT lens's dispatch. If `model` is
absent, omit the argument so the lens inherits the session model. This lets you run judgment-heavy
lenses on `opus` and mechanical ones on `haiku`/`sonnet` — a large cost lever when the transcript
is big (each lens reads it).

**First-party lenses** ship with eval-pack; dispatch each with the `Agent` tool using the matching
`subagent_type`, passing `PACK_DIR` (absolute), `REPO_ROOT`, and `DIFF_BASE`:

- `requirement-drift` (scorer) — did the delivered work match what the user originally asked?
  Default-on in `analysisLenses`. Its `delivered`/`unmet` arrays feed the Summary tab's
  "What changed" / "not proven" columns.
- `verification-rigor` (scorer) — were success claims backed by observed evidence?
  Default-on in `analysisLenses`. Its `proven`/`unproven` arrays feed the Summary tab's
  "What the transcript proves" / "not proven" columns.
- `review` (contributor) — adversarial review findings: bugs/risks in the delivered work,
  most-severe-first. Default-on in `analysisLenses` (see the config defaults).
- `business-risk` (contributor) — business/stakeholder risk of the delivered work: level,
  mitigation steps, and the biggest remaining uncertainty. Default-on in `analysisLenses`.
- `friction` (contributor) — developer-experience friction encountered during the session,
  classified into the configured `frictionCategories`. Default-on in `analysisLenses`. A
  deterministic gate (`validate_contracts.py`, run again at render time) rejects any entry whose
  `type` is not in `frictionCategories`.
- `repo-improvements` (contributor) — how the repo/codebase could be improved: tooling,
  structure, or docs gaps the session surfaced. Default-on in `analysisLenses`.
- `user-improvements` (contributor) — how well the developer OWNED the work: intent, engineering
  decisions, and the review/due-diligence the risk warranted (vs. offloading judgment to the AI —
  vibecoding, incl. letting the AI decide whether a check was even needed). Calls out strengths and
  improvements, each cited. Default-on in
  `analysisLenses`.
- `sycophancy` (contributor) — how sycophantic the assistant was toward the developer: flattery,
  agreement, or answer-changes decoupled from evidence, as a low/medium/high level with cited
  moments. Grounded in the sycophancy literature. Default-on in `analysisLenses`.

> Dispatch any other lens present in `analysisLenses` the same way, using its `skill` as the
> `subagent_type` suffix.

> Run the `<skill>` lens. PACK_DIR is `${ABS_PACK_DIR}`. REPO_ROOT is `${REPO_ROOT}`. DIFF_BASE is
> `${DIFF_BASE}`. TRANSCRIPT is `<resolved per-lens transcript path>`. Read the artifacts (read the
> transcript from TRANSCRIPT), then write your result to `${ABS_PACK_DIR}/lenses/<skill>.json` per
> your schema.

If the lens's declared view is `skeleton`, append the pull recipe to that dispatch prompt so the
lens knows how to fetch full turn bodies on demand:

> TRANSCRIPT is `${ABS_PACK_DIR}/views/skeleton.jsonl` (a skeleton — every turn's text, tool-call
> digests, and one-line result summaries; no bodies). RAW_TRANSCRIPT is
> `${ABS_PACK_DIR}/transcript.jsonl`. To read a turn's full body, run `"$PYTHON"
> "${CLAUDE_PLUGIN_ROOT}/scripts/pull_turn.py" "$RAW_TRANSCRIPT" <turnId> --field
> <text|thinking|tool_input|tool_result>`. Pull selectively.

Non-skeleton lenses' dispatch prompt is unchanged — they receive only the generic prompt above,
with no RAW_TRANSCRIPT and no pull recipe.

**Pre-turnId fallback.** If `${ABS_PACK_DIR}/transcript.jsonl` lacks a `turnId` on its first data
record (a pack built via the context-reconstruction fallback in Step 1), do NOT hand a skeleton
lens the skeleton view — pull-by-turnId can't work; pass its `TRANSCRIPT` as the raw
`${ABS_PACK_DIR}/transcript.jsonl` instead, so it reads the full transcript directly. Look-back
never breaks; it just degrades to reading the whole transcript for that one lens.

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
aggregated `finalScore` — the evaluator (next step) reads this to synthesize confidence, and
the report's Lenses tab renders it.

Guards: rules come from config set before the run sees results (G1, pre-committed); every result is
attributed and the aggregation math is written to lenses.json (G2, transparent); the rule was
bounded to a known, can-still-fail rule at resolve time (G3); lenses are config-listed only,
failures degrade to quarantined notes, and the core ran without them (G4, isolated).

## Step 4.5: Analyze (independent evaluator synthesizes lens findings)

The analysis must NOT be written by you — you did the work, and a self-graded
evaluation is not trustworthy evidence. Dispatch an independent evaluator instead.

By this point Step 4 has already run: `${PACK_DIR}/lenses.json` and `${PACK_DIR}/lenses/*.json`
exist (or `analysisLenses` was empty and neither exists — the Airplane Test). The evaluator is a
SYNTHESIZER: it does not re-derive a verdict a lens already owns (requirement drift, verification
rigor, review findings, business risk, friction) — it reads those findings plus `patterns.json`
flags and synthesizes `completionStatus` / `confidencePercent` / `confidenceNotes` from them.

**If analysis is enabled** (`analysis` in the resolved `eval-config.json`, default true):

Resolve `PACK_DIR` to an absolute path and capture the repo root before dispatching (reuse
`ABS_PACK_DIR`, `REPO_ROOT`, `DIFF_BASE` from Step 4 if this is the same run).

Ensure the evaluator's `skeleton` view exists (it may already have been built in Step 4 if a lens
requested it; if not, build it now):

    [ -f "${PACK_DIR}/views/skeleton.jsonl" ] || "$PYTHON" \
        "${CLAUDE_PLUGIN_ROOT}/scripts/build_views.py" "${PACK_DIR}/transcript.jsonl" \
        "${PACK_DIR}/views" skeleton \
        --tool-result-trunc-len "$(jq -r '.toolResultTruncLen // 400' "${PACK_DIR}/eval-config.json")"

If this build fails or the view can't be produced, continue anyway — the evaluator falls back to
reading `${ABS_PACK_DIR}/transcript.jsonl` directly (its TRANSCRIPT fallback), so a missing
skeleton view never blocks the run.

**Pre-turnId fallback.** If `${ABS_PACK_DIR}/transcript.jsonl` lacks a `turnId` on its first data
record (a pack built via the context-reconstruction fallback in Step 1), do NOT hand the evaluator
the skeleton view — pull-by-turnId can't work; resolve TRANSCRIPT to the raw
`${ABS_PACK_DIR}/transcript.jsonl` instead, and omit RAW_TRANSCRIPT and the pull recipe from the
dispatch prompt below. Look-back never breaks; it just degrades to reading the whole transcript.
Otherwise resolve TRANSCRIPT to `${ABS_PACK_DIR}/views/skeleton.jsonl`.

Dispatch the `eval-pack-evaluator` agent with the `Agent` tool, `subagent_type:
eval-pack-evaluator`. Pass it only the artifact location — not your own reasoning:

> Write the eval-pack analysis. PACK_DIR is `${ABS_PACK_DIR}` (absolute). REPO_ROOT is
> `${REPO_ROOT}`. DIFF_BASE is `${DIFF_BASE}`. TRANSCRIPT is `<resolved TRANSCRIPT path>`.
> Read eval-config.json (your configuration), TRANSCRIPT, metrics.json, patterns.json,
> test-results.json, `lenses.json`, and `lenses/*.json` from PACK_DIR — the lens findings are
> already computed; ingest them, do not re-derive their verdicts — run git from REPO_ROOT to
> inspect the diff against DIFF_BASE, and write `${ABS_PACK_DIR}/analysis.json` per your schema.

If TRANSCRIPT resolved to the skeleton view (the pre-turnId fallback did not apply), append the
pull recipe to that dispatch prompt so the evaluator knows how to fetch full turn bodies on demand:

> TRANSCRIPT is `${ABS_PACK_DIR}/views/skeleton.jsonl` (a skeleton — every turn's text, tool-call
> digests, and one-line result summaries; no bodies). RAW_TRANSCRIPT is
> `${ABS_PACK_DIR}/transcript.jsonl`. To fetch a turn's full body when a summary is insufficient to
> verify a lens finding's quote, run `"$PYTHON" "${CLAUDE_PLUGIN_ROOT}/scripts/pull_turn.py"
> "$RAW_TRANSCRIPT" <turnId> --field <text|tool_input|tool_result>`. Pull selectively.

If the pre-turnId fallback applied, the dispatch prompt is unchanged — no RAW_TRANSCRIPT, no pull
recipe.

Wait for the agent to finish. Confirm `${ABS_PACK_DIR}/analysis.json` exists and has a
`title`. If it is missing or empty, the evaluator failed — re-dispatch once; if it
fails again, stop and tell the user the analysis step failed. Do NOT write the
analysis yourself as a fallback — that reintroduces the bias this step exists to remove.

Then run the deterministic contract gate — it checks the analysis and test results against the
resolved config (retrospective answers, rubric band, test-command proof, and — now that lenses
have already run — the friction taxonomy check against `lenses/friction.json`):

```bash
"$PYTHON" "${CLAUDE_PLUGIN_ROOT}/scripts/validate_contracts.py" "${ABS_PACK_DIR}"
```

If it exits non-zero, route each `CONTRACT:` line to its owner:
- **Analysis violations** (retrospectiveAnswers / rubricApplied): re-dispatch the evaluator ONCE,
  passing those lines as corrections.
- **Test violations** (test-results.commands / verdict): the evaluator cannot fix these — redo
  Step 3 so `test-results.json` records every configured command with its real exit code and a
  verdict consistent with them.
- **Friction taxonomy violations** (`lenses/friction.json` entry type not in `frictionCategories`):
  re-dispatch the `friction` lens ONCE, passing the violation as a correction, then re-run
  `assemble_lenses.py`.
Re-run the gate. If it still fails, STOP and show the user the violations — do not render.
(render_html enforces the same gate again as the code-level backstop; skipping this step cannot
ship a non-conforming pack.)

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
