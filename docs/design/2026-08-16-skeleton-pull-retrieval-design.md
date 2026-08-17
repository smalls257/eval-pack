# Design: Skeleton view + pull-on-demand retrieval

**Date:** 2026-08-16
**Status:** Approved (brainstorming), pending spec review
**Branch:** `evalpack/transcript-projections` (continues the transcript-projections effort)
**Builds on:** the shipped view mechanism (`full`/`conversation`/`activity`), canonical `turnId`, and the top-level-field strip. Current floor: per-run token cost across 9 readers **94.6M → 24.2M (3.9×, −74%)** on a 42MB session.

---

## Problem

The condensed views still ingest their whole category wholesale. `activity` (6 of 9 readers) keeps every tool call and a truncated body for every tool result. Most of that is never needed: a lens usually confirms a claim from the *result summary* (exit code, pass/fail line) and only occasionally needs a full body. We are still paying to ingest bodies the lens won't read.

**Named failure mode:** Computational Friction (Engine) — ingest-everything-in-category instead of retrieving only what's relevant.

## Constraint that shapes the design: recall

A query/retrieval design can **miss** signal a fixed view would have shown (a grep pattern only finds what it anticipated). For an evaluator, missing signal is the worst failure — a Silent Fallback dressed as a pass ("grep found no failures → verification looks fine"). So the design's load-bearing invariant:

> **Recall is a property of the skeleton, not the pull decision.** The skeleton always shows *that* every turn and every tool call exists, plus each result's status/size. The model choosing not to pull a body only ever loses *depth*, never *awareness*. Pull-on-demand can therefore never make the lens blind to a turn — worst case it under-inspects a body it could see existed.

---

## Design

### 1. New view: `skeleton` (append-only vocabulary)

Vocabulary becomes `full` | `conversation` | `activity` | `skeleton`. It is opt-in per lens (frontmatter `inputs.transcript: skeleton`); lenses that don't want the pull-loop stay on their current view. `full` remains the safe default.

Per record, `skeleton` emits one compact entry:

- `turnId` + role
- full user/assistant **text** (the core graded signal; small)
- `tool_use` → tool **name** + an **input digest**: the salient identifier only — Bash→command line, Read/Edit/Write→path (+ byte-size of the full input). Not the full input body.
- `tool_result` → a **one-line summary**: exit/ok-fail status + first line + last line (each clipped short) + total byte-size. Enough to confirm pass/fail for the common case *without* a pull.
- **thinking dropped** (no lens grades the assistant's chain-of-thought; sycophancy is explicitly instructed to ignore it — verified 2026-08-16 across all 8 lenses + the evaluator). Pull-on-demand if ever needed.

The skeleton is ≈ `conversation`-sized or smaller.

### 2. Pull-on-demand tool

`scripts/pull_turn.py <transcript> <turnId> [--field text|thinking|tool_input|tool_result]` — a deterministic, tested extractor. Reads the pack's raw `transcript.jsonl` (which carries `turnId`), returns the requested turn's full body (or a named field). turnId-not-found → clean nonzero exit + stderr. This is the single place transcript-schema knowledge lives; the lens never hand-writes jq/grep (avoids the Leaky Narrative / schema-coupling trap where a log-format change breaks every lens).

**The model decides *when/what* to pull; the tool does the extraction deterministically.** The lens is told: read the skeleton; run `pull_turn` for a turn only when its summary flags a reason (exit≠0, backing you must confirm against the body, a span you must quote). Pull selectively — do not pull everything.

### 3. Dispatch & wiring

The dispatcher hands a `skeleton` lens **two paths**:
- `TRANSCRIPT` = `${PACK_DIR}/views/skeleton.jsonl`
- `RAW_TRANSCRIPT` = `${PACK_DIR}/transcript.jsonl` (the pull source)

`generate` Step 4 already computes `requested_views` from lens frontmatter and builds only those — `skeleton` joins that set. The dispatch prompt template gains the `RAW_TRANSCRIPT` line for skeleton lenses (a `full`/view lens ignores it).

**`tune` is wired the same way** (build the requested views incl. skeleton, pass `TRANSCRIPT` + `RAW_TRANSCRIPT`). This closes the gap where re-evaluation of an existing pack currently reads the full transcript with no savings. (Note: an old pack whose stored `transcript.jsonl` predates `turnId` can't support pull-by-turnId; such a lens falls back to reading `RAW_TRANSCRIPT` directly — correct, just unoptimized.)

### 4. Recall guarantee (structural)

- Every turn appears in the skeleton (only thinking-only content is thinned, and thinking is pull-able).
- Every `tool_use` appears (name + digest) — the lens always knows a tool ran and what it was.
- Every `tool_result` appears as a summary with status + size — the lens always knows a result exists and whether it looks pass/fail, and can pull the body.

So "did the lens notice X happened" is guaranteed by the skeleton; only "did it read X's full body" is the model's (pullable) choice.

### 5. Lens prompt shape (pilot: `verification-rigor`)

Its body changes from "read the transcript" to: read the `skeleton` at `TRANSCRIPT`; for each success claim, the result summary usually shows whether a backing command ran and passed; when the summary is ambiguous or you must quote the evidence, `pull_turn.py "$RAW_TRANSCRIPT" <turnId> --field tool_result`. Score from what you observe; pull selectively. Its output contract/schema is unchanged.

---

## Acceptance gates (both required per converted lens)

1. **Verdict consistency** — an A/B (skeleton+pull vs full-read) on real recorded sessions reaches the same verdict/score-band and the same core `proven`/`unproven` (or level/findings) set, within normal LLM run-to-run variance. This is the exact protocol already run for `verification-rigor` (full [90,94] vs activity [93,96], same 5 proven claims).
2. **Net token savings** — measured `skeleton size + realized pull tokens < the lens's current view cost`. Over-pulling would defeat the point, so this is measured on the A/B sessions, not assumed.

A converted lens ships only when both gates pass; otherwise it stays on its current view.

## Rollout

1. Build the `skeleton` projection + `pull_turn.py` + dispatch/tune wiring.
2. **Pilot `verification-rigor`** (A/B baseline exists). Prove both gates.
3. Expand to the other `activity` lenses one at a time, each gated on both acceptance checks.
4. `conversation` lenses may stay (already cheap) or move later.

## Backward compatibility

- Additive: a 5th opt-in view; unconverted lenses and the default (`full`) are untouched.
- `render_html` still reads the raw full transcript — viewing existing packs is unchanged.
- `pull_turn` needs `turnId` in the transcript; new packs have it, old packs fall back to reading `RAW_TRANSCRIPT` directly.

## Testing

- **Unit:** `skeleton` per-record projection (text kept, tool_use digested, tool_result summarized with status/size, thinking dropped, turnId preserved); `pull_turn.py` (returns the right turn/field, unknown turnId → nonzero exit, field selector).
- **Integration:** `generate`/`tune` build `skeleton` when requested and pass both paths; a skeleton lens can pull a turn end-to-end.
- **Acceptance:** the two gates above, scripted as a repeatable A/B harness (dispatch the lens both ways on N recorded sessions, diff verdicts, sum pull tokens).

## Explicitly out of scope

- Lens-declared grep/regex extraction recipes (rejected — Leaky Narrative + recall risk owned by the author). The model-decides-pull design keeps extraction deterministic without coupling lenses to the schema.
- Converting `conversation` lenses to skeleton (later, if worthwhile).
- A live deterministic runtime quote gate (unchanged from prior scope).
