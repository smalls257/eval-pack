# Design: Efficiency Phase 2 — cost ledger, batch pulls, delta reuse

**Date:** 2026-08-16
**Status:** Approved (brainstorming), pending spec review
**Branch:** continues `evalpack/transcript-projections` (or a fresh branch off it)
**Builds on:** the shipped transcript-view + skeleton work. Those cut *what each reader ingests* (per-run ~4.4×). This phase adds an **instrument** and two **deterministic** cost levers that the view work can't reach.

---

## Problem

Three gaps, established by grounding against the code:

1. **eval-pack doesn't meter its own spend.** `extract_metrics.py` records token usage of the *evaluated* session, but the Step-4 lens dispatches never record eval-pack's *own* per-lens cost — even though every Agent tool result already carries `subagent_tokens: N` (`extract_metrics.py:11` parses exactly this field, for the other session). You can't tune spend you can't see. **Named failure mode:** Black Box (Sensor) — optimizing the pipeline blind.
2. **The tool-loop tax.** `pull_turn.py` is one-turnId-per-full-file-scan (`pull_turn.py:17-31,64-67`); N pulls = N scans, each an agentic round-trip that re-bills accumulated context. **Named failure mode:** Computational Friction (Engine).
3. **No reuse across re-runs.** `tune` always re-dispatches *all* configured lenses (`tune/SKILL.md:81-87`); the only reuse is manual single-lens mode. There is zero content-hash keying of lens *outputs* (`lens-versions.json` hashes the lens `.md` for the drift gate, not outputs). Regenerating a pack after a trivial change re-pays the whole lens bill. **Named failure mode:** Computational Friction — recompute-everything instead of recompute-what-changed.

## Sequencing

**A (ledger) → B (batch pulls) → C (delta reuse).** The ledger is first because it makes B's and C's savings measurable, and C's reused-vs-recomputed decisions surface as ledger lines.

---

## Feature A — Cost ledger

Record eval-pack's own per-lens token spend and render it.

### Capture
The per-lens count lives only in the **parent** (orchestrator) Agent tool result — a lens subagent cannot see its own usage. So during generate Step 4 (lens dispatch) and Step 4.5 (evaluator dispatch), the orchestrator writes a **one-integer sidecar** per dispatch: `${PACK_DIR}/lenses/<skill>.cost.json` = `{"skill": ..., "tokens": <subagent_tokens>, "model": <model>}`. The orchestrator's only job is copying the integer it just received.

**Spike (plan task 1):** determine whether a deterministic script can instead parse the *generate session's own* transcript for these Agent tool results (reusing `extract_metrics.extract_subagent_tokens`), eliminating the LLM copy entirely. If the current session's transcript path is cleanly locatable at run time, prefer that and drop the sidecar. If not, keep the sidecar. **Either way, aggregation and render are deterministic** — the LLM never does math, only (at most) copies one integer per lens.

### Aggregate (deterministic)
New `scripts/pack_cost.py`:
- Input: the sidecars (or the parsed session transcript, per the spike).
- Output: `${PACK_DIR}/pack-cost.json`:
  ```json
  {
    "perLens": [{"skill": "sycophancy", "tokens": 44155, "model": "sonnet", "reused": false}],
    "evaluatorTokens": 51000,
    "totalTokens": 220000
  }
  ```
- Validates each entry (integer tokens, known skill). A missing/malformed sidecar is a recorded gap, never a silent zero (no Silent Fallback — a lens with no cost record is flagged, not treated as free).
- `reused` is populated from Feature C's fingerprint decision (a reused lens has `tokens: 0, reused: true`), so the ledger shows realized savings.

### Render
`render_html.py` already threads `metrics.json` into the template (`render_html.py:723,742`); the client renders stat groups in `scripts.js:217-254`. Add:
- a **"Cost of this pack"** stats group (per-lens spend + evaluator + total), mirroring the existing `Subagent tokens` group (`scripts.js:238-241`);
- read `pack-cost.json` the same way `metrics.json` is read.

### v1 scope
Tokens per lens + model + total + reused flag. **Out of scope for v1:** cache-read/write split, dollar estimate, wall-clock — additive later once the sensor exists.

---

## Feature B — Batch pulls (only)

Cut the N-scans-for-N-turns tax; no view pre-splitting (skeleton already made view reads small, and pre-splitting reduces round-trips without reducing bytes — not worth the complexity).

### `pull_turn.py --ids`
- Add `--ids 12,47,301` (comma-separated). One linear scan of the transcript collects the whole requested set (vs `_record` returning on first match, `pull_turn.py:17-31`), applies the `--field` selector per id, and emits **labeled per-id output** (e.g. a small JSON object `{turnId: body}` or `=== turn N ===` delimiters — the exact format is a plan decision, but it must be unambiguous to split).
- Single positional `turn_id` stays as-is (back-compat; existing lens prompts keep working).
- Unknown ids in a batch: report which were missing (don't fail the whole batch silently — a missing id is a finding, not a no-op).

### Prompt nudge
In the skeleton-view lenses' pull instructions (`verification-rigor.md:24-25`, `sycophancy.md:48-51`, etc.), add: "If you need several turns' bodies, collect the turnIds and pull them in **one** `--ids` call rather than one at a time." Worst case the lens still pulls one-at-a-time → no regression.

---

## Feature C — Delta reuse (C1 + C2), keyed by content not turnId

Reuse a prior round's lens output when the lens's actual inputs are byte-identical. **Explicitly not turn-level delta (C3):** turnId is a post-sort ordinal (`merge_sessions.py:49-51`) that shifts whenever the merged input set's membership or ordering changes (added prior session, new earlier-timestamped subagent file, dropped deduped uuid) — and drift lenses grade the whole conversation and can't delta by turn. Content-hash reuse sidesteps all of that.

### Fingerprint
New `scripts/pack_fingerprint.py`:
- **Per-lens key** = `sha256(view-file bytes ∥ lens-version ∥ model ∥ diff-base)`. The view-file bytes are the lens's *actual* input (already built by `build_views.py`), so any transcript change that alters what the lens sees flips the key. `lens-version` (from `lens-versions.json`) flips when the lens `.md` changes. `model` flips when the tier changes. `diff-base` flips when the reviewed diff changes (matters for lenses that read `repo-diffs.json`).
- **Whole-pack key** = the ordered digest of all per-lens keys + the resolved config hash.
- Written to `${PACK_DIR}/pack-fingerprint.json` each run.

### Reuse decision (generate + tune)
Before dispatching a lens:
- Load the prior round's `pack-fingerprint.json` from the persisted pack dir (render no longer deletes it — `render_html.py:804`).
- **Per-lens key matches AND `lenses/<skill>.json` exists on disk → skip the dispatch, keep the on-disk result** (mark it `reused` for the ledger).
- **Mismatch or missing prior → dispatch** (overwrites `lenses/<skill>.json`).
- **C1 fast path:** if the whole-pack key matches → skip *every* lens dispatch and the evaluator, reuse all on-disk outputs, go straight to render.

Leans entirely on existing plumbing: persisted pack dir, per-lens files that a re-dispatch overwrites, and config-gated assembly (`assemble_lenses.py:66-72` orphan guard already ignores unconfigured leftovers).

### Safety properties
- **No turnId dependency** — the key hashes view bytes, so the citation-coordinate-shift landmine never applies to the reuse decision.
- **Drift lenses safe** — a whole-conversation lens's view bytes change whenever any graded turn changes, so it can never be wrongly reused.
- **Fail-safe default** — a missing/unreadable prior fingerprint means *no* reuse (re-run everything), never a stale-reuse (no Silent Fallback: uncertainty forces recompute, not a fake-fresh result).
- **Transparency (Sensor)** — reused results are stamped `reused: true`; the ledger reports `tokens: 0` for them, so the pack shows exactly what was recomputed vs reused.

---

## How the three compound

- The **ledger** turns C's savings from a claim into a measured number (`reused` lenses show `tokens: 0`).
- **C** is the big amortized win on the regenerate/tune axis (70–90% off a re-run where inputs are unchanged); **0** on a fresh generate.
- **B** is a small deterministic token win + a real wall-clock win on pulling lenses.
- All three are **deterministic** — no model-quality gamble, so none needs an A/B gate (unlike the cheap-first / candidate-mining ideas that were deferred).

## Testing

- **A:** unit — `pack_cost.py` aggregation (sidecars → totals; malformed sidecar → recorded gap not zero). Integration — a generate run produces `pack-cost.json` with one entry per dispatched lens; render shows the group.
- **B:** unit — `pull_turn --ids` returns the same bodies as N single pulls, labeled and splittable; unknown id reported; single-id back-compat unchanged.
- **C:** unit — `pack_fingerprint` key flips on each input axis (view bytes, lens-version, model, diff-base) and is stable when all are unchanged; whole-pack key. Integration — second identical run reuses all lenses (C1); changing one lens `.md` re-runs only that lens (C2); a transcript change re-runs the affected lenses; a missing prior fingerprint re-runs everything.
- **Regression:** full suite stays green; a fresh generate with no prior fingerprint behaves exactly as today.

## Out of scope (deferred)

- Turn-level delta (C3) — unsafe per the turnId analysis.
- View pre-splitting — marginal vs skeleton.
- Cheap-first model escalation, deterministic candidate mining, output-token narrator — all need A/B gates (model-quality gambles); revisit after the deterministic wins land and the ledger can measure them.
- Batch API / shared-prefix caching — require the agentic-app rewrite (out of the CLI-plugin model).
