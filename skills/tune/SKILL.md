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

Read `analysisLenses` from `${PACK_DIR}/eval-config.json`. If it is empty, skip lens dispatch
entirely (the Airplane Test) and go straight to `assemble_lenses.py` below. Otherwise resolve the
same identifiers generate Step 4 does:

```bash
ABS_PACK_DIR=$(cd "${PACK_DIR}" && pwd)
REPO_ROOT=$(git rev-parse --show-toplevel)
if git rev-parse HEAD~1 >/dev/null 2>&1; then
    DIFF_BASE="HEAD~1"
else
    DIFF_BASE="4b825dc642cb6eb9a060e54bf8d69288fbee4904"
fi
```

**Build the transcript views (cost lever)** — the same block generate Step 4 uses, so a tune re-run
gets the same token savings as the original run:

```bash
VIEWS=$("$PYTHON" "${CLAUDE_PLUGIN_ROOT}/scripts/lens_inputs.py" \
    "${CLAUDE_PLUGIN_ROOT}/agents/lenses" "${PACK_DIR}/eval-config.json")
# $VIEWS is intentionally left unquoted below — it must word-split into separate
# positional args for build_views.py; quoting it would pass one empty/combined arg instead.
if [ -n "$VIEWS" ]; then
    "$PYTHON" "${CLAUDE_PLUGIN_ROOT}/scripts/build_views.py" \
        "${PACK_DIR}/transcript.jsonl" "${PACK_DIR}/views" $VIEWS \
        --tool-result-trunc-len "$(jq -r '.toolResultTruncLen // 400' "${PACK_DIR}/eval-config.json")"
fi
```

If every configured lens declares `full` (or no `inputs.transcript`), `$VIEWS` is empty and this
block is a no-op — no `views/` dir, no `build_views.py` call.

**Delta reuse — compute the fingerprint and decide what to skip.** Same gate as generate Step 4,
same reason: the pack dir was just restored from the zip and may already carry a
`pack-fingerprint.json` from the round that produced it, so preserve it BEFORE recomputing or the
comparison degenerates to prior-equals-current and nothing would ever re-run:

```bash
if [ -f "${PACK_DIR}/pack-fingerprint.json" ]; then
    mv "${PACK_DIR}/pack-fingerprint.json" "${PACK_DIR}/pack-fingerprint.prev.json"
fi
"$PYTHON" "${CLAUDE_PLUGIN_ROOT}/scripts/pack_fingerprint.py" "${PACK_DIR}" \
    --config "${PACK_DIR}/eval-config.json" --diff-base "${DIFF_BASE}"
DECISION=$("$PYTHON" "${CLAUDE_PLUGIN_ROOT}/scripts/pack_fingerprint.py" \
    --decide "${PACK_DIR}/pack-fingerprint.prev.json" "${PACK_DIR}/pack-fingerprint.json")
```

**Fail-safe:** if no prior `pack-fingerprint.json` existed (or it was unreadable), `--decide`
already returns `reuseAll: false` with an empty `reuse` set — dispatch ALL lenses and the
evaluator, never reuse on uncertainty. (`--decide` hard-fails loudly, by design, if the
freshly-written CURRENT fingerprint is malformed — a real bug worth surfacing, not something to
paper over with a shell fallback.)

This is exactly the point of `tune`: editing `.eval-pack.json` (a rubric, a stance, a
`frictionCategories` list, a lens's `model`) is a config change, and `pack_fingerprint.py` folds
the resolved config bytes into EVERY per-lens key (not just `whole`) — so any `eval-config.json`
change re-runs all lenses, never a silent reuse, even for a lens whose config-derived behavior
(like `friction`'s `frictionCategories`) isn't reflected in any view file. Only lenses whose
ACTUAL inputs (view bytes, lens version, model, diff base, resolved config) are byte-identical to
the prior round are eligible to skip.

**C1 — whole-match fast path.** If `DECISION.reuseAll` is `true` (config unchanged, no lens `.md`
edited, no evaluator edit, transcript unchanged since the pack was captured — the common case when
`tune` is invoked for something unrelated, e.g. re-rendering), skip ALL lens dispatches, the
`assemble_lenses.py` call, AND the evaluator dispatch below; keep the on-disk `analysis.json` and
`lenses/*.json`/`lenses.json` as-is (nothing changed, so nothing needs re-assembling). Write reused
cost sidecars (`{"tokens": 0, "reused": true}`) for every configured lens plus
`eval-pack-evaluator` (if `analysis` is enabled), still run `pack_cost.py` to refresh
`pack-cost.json`, then go straight to Step 4 (re-render).

**C2 — per-lens match.** Otherwise, for each configured lens: if its `skill` is in
`DECISION.reuse` AND `${PACK_DIR}/lenses/<skill>.json` exists, skip dispatching it — keep the
on-disk result — and write its cost sidecar as `{"tokens": 0, "reused": true}`. Dispatch every
other lens (in `DECISION.rerun`) normally, with its real cost sidecar. The evaluator ALWAYS
re-runs in this branch (only C1 skips it), since lens outputs it synthesizes from may have changed.

Then, for each configured lens: **apply the C2 reuse check above first** — if it's skipped, keep
its on-disk `lenses/<skill>.json` and its already-written `reused: true` cost sidecar, and move on.
Otherwise dispatch it, EXACTLY as generate Step 4 specifies for a non-skipped lens,
including its per-lens `TRANSCRIPT` resolution: declared view → `${ABS_PACK_DIR}/views/<view>.jsonl`;
`full` or no declared view → `${ABS_PACK_DIR}/transcript.jsonl` (unchanged from today — the
non-skeleton, full-view re-eval path still just reads the recorded transcript). For a `skeleton`
lens, also pass `RAW_TRANSCRIPT = ${ABS_PACK_DIR}/transcript.jsonl` and append the pull_turn recipe
to its dispatch prompt, exactly as generate Step 4's skeleton addendum does. Non-skeleton lenses'
dispatch prompt is unchanged — no `RAW_TRANSCRIPT`, no pull recipe.

**Pre-turnId fallback.** If `${PACK_DIR}/transcript.jsonl` lacks `turnId` (check the first data
record for a `turnId` key — a pack recorded before the turnId change), a `skeleton` lens cannot
pull turn bodies by id. In that case pass that lens's `TRANSCRIPT` as the raw
`${ABS_PACK_DIR}/transcript.jsonl` directly (skip the skeleton view and RAW_TRANSCRIPT/pull recipe
for it) — it reads the full transcript like a `full` lens would. Look-back never breaks; it just
degrades to reading the whole transcript for that one lens.

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

**Minor refinement:** this mode has always unconditionally dispatched `LENS`, since the whole point
was iterating on that lens. Now that Step 3 computes a fingerprint anyway, if `LENS` itself is in
`DECISION.reuse` (its declared view, lens version, model, and diff base are all byte-identical to
the prior round — e.g. the invocation targeted the wrong lens, or was re-run with no edit), it too
may be skipped with the same reused-cost-sidecar treatment. This is optional — dispatching it
unconditionally (today's behavior) is always safe, just occasionally redundant.

1. **Validate.** Read the resolved `analysisLenses` from `${PACK_DIR}/eval-config.json`. If `LENS`
   is not among the configured `skill` values, STOP with a precise error: `lens '<skill>' is not in
   analysisLenses — nothing to tune`. Do not invent a lens or fall back to running all of them.

2. **Ensure the prior round is on disk.** `render_html.py` now persists the pack dir after a
   successful render, so the prior round's `lenses/*.json`, `lenses.json`, `analysis.json`,
   `metrics.json`, etc. are normally already present under `${PACK_DIR}` from Step 1. If
   `${PACK_DIR}` or its `lenses/` subdir is missing (first tune after upgrading, or the dir was
   cleaned), restore it from the existing zip exactly as Step 1 does — `rm -rf "$PACK_DIR" && unzip
   -qo "$ZIP" -d "$OUTPUT_DIR"` — then continue.

3. **Build the view, then dispatch ONLY the target lens.** Before dispatching, run Step 3's
   view-build block (`lens_inputs.py` + `build_views.py`, guarded by `[ -n "$VIEWS" ]`) so the
   target lens's declared view exists — a harmless no-op if it declares `full`, or if the view is
   already on disk from the prior round (rebuilding just overwrites it with the same content).
   Then follow Step 3's dispatch mechanics for that one lens only — same `subagent_type` (the
   lens's `skill`), same `PACK_DIR`/`REPO_ROOT`/`DIFF_BASE` arguments, the lens's configured
   `model` if it has one, and the same per-lens `TRANSCRIPT` resolution (declared view →
   `${ABS_PACK_DIR}/views/<view>.jsonl`; `full`/none → `${ABS_PACK_DIR}/transcript.jsonl`). If it
   is a `skeleton` lens, also pass `RAW_TRANSCRIPT = ${ABS_PACK_DIR}/transcript.jsonl` plus the
   pull_turn recipe — or, if `${PACK_DIR}/transcript.jsonl` lacks `turnId`, apply the pre-turnId
   fallback above (pass `TRANSCRIPT` as the raw transcript instead). It overwrites
   `${PACK_DIR}/lenses/<LENS>.json`. Do NOT dispatch the other configured lenses — that is the
   entire point of this mode.

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
