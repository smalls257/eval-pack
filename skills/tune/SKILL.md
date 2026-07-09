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
SID=$(unzip -l "$ZIP" | awk 'NR==4{print $4}' | cut -d/ -f1)
PACK_DIR="${OUTPUT_DIR}/${SID}"
rm -rf "$PACK_DIR" && unzip -qo "$ZIP" -d "$OUTPUT_DIR"
```

If no zip exists, STOP: "no pack to tune — run /eval-pack:generate first."
If `${PACK_DIR}/transcript.jsonl` is missing (pack was built with `includeTranscript: false`),
STOP and say so: tuning needs the recorded transcript — regenerate with it enabled.

## Step 2: Re-resolve configuration (picks up your edits, fail-loud)

```bash
"$PYTHON" "${CLAUDE_PLUGIN_ROOT}/scripts/resolve_config.py" "$(pwd)" "${PACK_DIR}"
```

Non-zero exit: STOP and show stderr verbatim.

## Step 3: Re-run the config-driven stages

```bash
"$PYTHON" "${CLAUDE_PLUGIN_ROOT}/scripts/detect_patterns.py" "${PACK_DIR}/transcript.jsonl" "${PACK_DIR}" --config "${PACK_DIR}/eval-config.json"
```

Then, if `analysis` is true in the resolved config: dispatch the independent evaluator and run the
contract gate EXACTLY as `skills/generate/SKILL.md` Step 4 specifies — same agent, same prompt
(PACK_DIR resolved to an absolute path, REPO_ROOT, DIFF_BASE), same
`validate_contracts.py` gate immediately afterward with the same re-dispatch-once-on-violation
rule, so the new analysis reflects the tuned stance/rubric/questions. If `analysis` is false, keep
the existing `analysis.json` (Step 4's disabled-stub path also applies here if you're switching
`analysis` from true to false).

Then run the lens step EXACTLY as generate Step 4.7 specifies (dispatch configured lenses, then):

```bash
"$PYTHON" "${CLAUDE_PLUGIN_ROOT}/scripts/assemble_lenses.py" "${PACK_DIR}"
```

## Step 4: Re-render (appends a new round to the same zip)

```bash
"$PYTHON" "${CLAUDE_PLUGIN_ROOT}/scripts/render_html.py" "${OUTPUT_DIR}" "${SID}" "${CLAUDE_PLUGIN_ROOT}" "${PACK_DIR}/transcript.jsonl" --branch "${BRANCH}"
```

## Step 5: Report the delta

Compare the previous round's headline (confidence, flags) with the new one and tell the user what
their config change did — e.g. "confidence 68 → 61 (new min aggregation); scopeDrift flag now off;
2 new detector flags". Print the `Open:` link.
