---
description: Re-evaluate an existing eval pack with your current .eval-pack.json — the fast tuning loop for rubric/stance/lens/detector changes. Reuses recorded facts; re-runs only evaluation and rendering, appending a new round. Can also re-run a SINGLE lens (e.g. "tune only the sycophancy lens") against the prior round's on-disk outputs without regenerating the whole pack.
tags: ["eval", "tune", "config"]
---

# Tune Eval Pack

Re-evaluate an existing pack with the CURRENT configuration. Facts (transcript, metrics, tools,
test results) are reused verbatim; only config-driven stages re-run. Use after editing
`.eval-pack.json` — the round history in the report shows old vs new side by side.

## Prerequisites

```bash
PYTHON="${CLAUDE_PLUGIN_OPTION_pythonExecutable:-python3}"
"$PYTHON" --version
```

## Step 1: Locate and unpack the existing pack

```bash
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
OUTPUT_DIR=<outputDir from resolved config; default .eval-packs>
ZIP=$(ls -t "${OUTPUT_DIR}"/*.zip 2>/dev/null | head -1)   # or the zip the user names
SID=$(unzip -Z1 "$ZIP" | head -1 | cut -d/ -f1)
PACK_DIR="${OUTPUT_DIR}/${SID}"
rm -rf "$PACK_DIR" && unzip -qo "$ZIP" -d "$OUTPUT_DIR"
```

If no zip exists, STOP: "no pack to tune — run /eval-pack-next:generate first."
If `${PACK_DIR}/transcript.jsonl` is missing (pack was built with `includeRawTranscript: false`,
the default), STOP and say so: tuning needs the recorded raw transcript — regenerate with
`includeRawTranscript: true`.

## Step 2: Re-resolve configuration (picks up your edits, fail-loud)

```bash
"$PYTHON" "${CLAUDE_PLUGIN_ROOT}/scripts/resolve_config.py" "$(pwd)" "${PACK_DIR}"
```

Non-zero exit: STOP and show stderr verbatim.

## Step 3: Re-run the config-driven stages

```bash
"$PYTHON" "${CLAUDE_PLUGIN_ROOT}/scripts/detect_patterns.py" "${PACK_DIR}/transcript.jsonl" "${PACK_DIR}" --config "${PACK_DIR}/eval-config.json"
```

First run the lens step EXACTLY as `skills/generate/SKILL.md` Step 4 specifies — dispatch every
lens configured in `analysisLenses` (or skip cleanly if empty), then:

```bash
"$PYTHON" "${CLAUDE_PLUGIN_ROOT}/scripts/assemble_lenses.py" "${PACK_DIR}"
```

The evaluator is a synthesizer that reads lens findings, so lenses must be re-run before it —
tuning a lens-affecting knob (e.g. `analysisLenses`, `frictionCategories`, `verdictAggregation`)
without re-running this step would leave the evaluator reading stale lens output.

Then, if `analysis` is true in the resolved config: dispatch the independent evaluator and run the
contract gate EXACTLY as `skills/generate/SKILL.md` Step 4.5 specifies — same agent, same prompt
(PACK_DIR resolved to an absolute path, REPO_ROOT, DIFF_BASE, reading `lenses.json` and
`lenses/*.json`), same `validate_contracts.py` gate immediately afterward with the same
re-dispatch-once-on-violation rule, so the new analysis reflects the tuned stance/rubric/questions
AND the freshly re-run lens findings.

If `analysis` is false in the resolved config: when the unpacked `analysis.json` is already a
disabled stub, leave it; when you are SWITCHING analysis from true to false, WRITE the disabled
stub exactly as generate Step 4.5's disabled path specifies (do not keep the old full analysis —
it may disagree with the tuned config and the render gate would refuse).

## Single-lens mode (optional)

If the invocation names a single lens — a `lens=<skill>` argument, or a clear user request like
"tune only the sycophancy lens" — set `LENS=<skill>` and follow this path instead of re-running
every configured lens in Step 3. It is the fast loop for iterating on ONE lens's rubric/prompt: it
dispatches only that lens and reuses everything else already on disk from the prior round.

1. **Validate.** Read the resolved `analysisLenses` from `${PACK_DIR}/eval-config.json`. If `LENS`
   is not among the configured `skill` values, STOP with a precise error: `lens '<skill>' is not in
   analysisLenses — nothing to tune`. Do not invent a lens or fall back to running all of them.

2. **Ensure the prior round is on disk.** `render_html.py` now persists the pack dir after a
   successful render, so the prior round's `lenses/*.json`, `lenses.json`, `analysis.json`,
   `metrics.json`, etc. are normally already present under `${PACK_DIR}` from Step 1. If
   `${PACK_DIR}` or its `lenses/` subdir is missing (first tune after upgrading, or the dir was
   cleaned), restore it from the existing zip exactly as Step 1 does — `rm -rf "$PACK_DIR" && unzip
   -qo "$ZIP" -d "$OUTPUT_DIR"` — then continue.

3. **Dispatch ONLY the target lens.** Follow Step 3's dispatch mechanics for that one lens only —
   same `subagent_type` (the lens's `skill`), same `PACK_DIR`/`REPO_ROOT`/`DIFF_BASE` arguments, and
   the lens's configured `model` if it has one. It overwrites `${PACK_DIR}/lenses/<LENS>.json`. Do
   NOT dispatch the other configured lenses — that is the entire point of this mode.

4. **Reuse the rest.** Do NOT re-run the other lenses, and do NOT re-dispatch the evaluator — reuse
   the on-disk `analysis.json` as-is. Note: if `LENS` is a `scorer`, `assemble_lenses.py`
   re-aggregates `finalScore` from the fresh score automatically, but the evaluator's prose still
   reflects the prior round; re-run the evaluator too only if the user explicitly wants fresh
   synthesis. A `contributor` lens (e.g. `sycophancy`) never touches the verdict, so reusing
   everything else is exact, not an approximation.

5. **Assemble, gate, and render — same as a normal tune.**

   ```bash
   "$PYTHON" "${CLAUDE_PLUGIN_ROOT}/scripts/assemble_lenses.py" "${PACK_DIR}"
   "$PYTHON" "${CLAUDE_PLUGIN_ROOT}/scripts/validate_contracts.py" "${ABS_PACK_DIR}"
   "$PYTHON" "${CLAUDE_PLUGIN_ROOT}/scripts/render_html.py" "${OUTPUT_DIR}" "${SID}" "${CLAUDE_PLUGIN_ROOT}" "${PACK_DIR}/transcript.jsonl" --branch "${BRANCH}"
   ```

   This appends a new round to the zip, same as the all-lens path. `assemble_lenses.py`'s orphan
   guard only assembles lenses present in `analysisLenses`, so a persisted pack dir that happens to
   hold output from lenses no longer configured cannot leak into the round.

## Step 4: Re-render (appends a new round to the same zip)

```bash
"$PYTHON" "${CLAUDE_PLUGIN_ROOT}/scripts/render_html.py" "${OUTPUT_DIR}" "${SID}" "${CLAUDE_PLUGIN_ROOT}" "${PACK_DIR}/transcript.jsonl" --branch "${BRANCH}"
```

If render exits non-zero with `CONTRACT:` lines, the pack dir is preserved unchanged — the tuned
config disagrees with the recorded artifacts. STOP and show the user the violations verbatim.

## Step 5: Report the delta

Compare the previous round's headline (confidence, flags) with the new one and tell the user what
their config change did — e.g. "confidence 68 → 61 (new min aggregation); scopeDrift flag now off;
2 new detector flags". Print the `Open:` link.
