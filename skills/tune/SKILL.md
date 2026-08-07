---
description: Re-evaluate an existing eval pack with your current .eval-pack.json — the fast tuning loop for rubric/stance/lens/detector changes. Reuses recorded facts; re-runs only evaluation and rendering, appending a new round.
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

If no zip exists, STOP: "no pack to tune — run /eval-pack:generate first."
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
