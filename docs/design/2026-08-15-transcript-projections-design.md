# Design: Extensible transcript projections for lenses

**Date:** 2026-08-15
**Status:** Approved (brainstorming), pending spec review
**Topic:** Cut lens token consumption via shared, deterministic, extensible transcript views

---

## Problem

Every lens subagent independently `Read`s the entire `transcript.jsonl` (measured up to
**42 MB**), and a 9th reader — the `eval-pack-evaluator` synthesizer — reads it again. No shared
preprocessing. Token consumption is heavy and expensive.

Measured composition of a 42 MB transcript:

| Chunk | % of bytes |
|---|---|
| Visible user + assistant **text** (the actual graded signal) | ~5% |
| tool_result payloads (file dumps, logs) | ~23% |
| thinking blocks | ~9% |
| tool_use inputs | ~5% |
| structural noise (attachments, file-history-snapshot, queue-operation, mode, …) | ~21% |

**~95% of every lens's tokens are not conversation.** Each of 9 readers pays to tokenize
multi-MB file dumps and structural noise it never grades.

**Named failure mode:** Computational Friction (Engine) — the same heavy input re-tokenized N times
with no shared projection; scale-by-tier instead of scale-by-thinking.

## Constraint that shapes the design: extensibility

Lenses are extensible — a third-party author drops a new `.md` into `agents/lenses/` and it must
work. Any fix that hardcodes "what today's 8 lenses need" is a **Distributed Monolith**: adding one
lens would force edits in a shared preprocessing module, breaking **Shield** (lenses must be
atomically addable). A projection that strips-by-default would **silently starve** a naive new lens
(Silent Fallback — wrong scores, no signal).

**Resolution — inversion of control.** The projector does NOT know lenses exist. It publishes a
small, versioned **view vocabulary**. Each lens *declares* which view it consumes. New lens = pick a
string; zero framework change.

---

## Design

### 1. View vocabulary (exactly 3, append-only)

| View | Contents | Typical consumers |
|---|---|---|
| `full` | Raw transcript.jsonl, unchanged. **Default.** | anything needing attachments/file-history; escape hatch |
| `conversation` | Real user + assistant text + thinking. No tool payloads, no structural noise. | sycophancy, requirement-drift, user-improvements, business-risk |
| `activity` | `conversation` + tool_use name/input + **truncated** tool_result + exit codes. | verification-rigor, review, repo-improvements, friction, evaluator |

- **Thinking is baked into `conversation` and `activity`, not a separate axis.** A thinking on/off
  knob is a boolean-flag God Method at the vocabulary layer (2 views × 2 = 4 products, next axis = 8).
  Thinking is ~9% — cheap enough to include unconditionally.
- **The vocabulary is append-only.** Changing the *meaning* of an existing view (e.g. dropping
  thinking from `conversation`) ships as a **new name**, never a mutation. Old names never break.
- **`full` is always available**, so no future lens can ever be *blocked* by the projection system —
  worst case it declares `full` and pays, identical to today. The projection is a pure fast-path over
  a safe default.

### 2. Lens declaration (frontmatter)

Map-valued from day one so future artifacts (diff, metrics) can be added without a second migration:

```yaml
inputs:
  transcript: activity      # one of: full | conversation | activity
```

- **Unspecified → `full`**, plus one build-time notice carrying the price tag:
  `lens 'foo': no view declared → full (42 MB)`. This is the **Sensor** move — "author chose
  expensive" must be distinguishable from "author didn't know."
- **Explicit `inputs.transcript: full` → silent.** The escape hatch means the nudge never nags.

### 3. Canonical turn IDs (coordinate system) — prerequisite

Today's built `transcript.jsonl` is stripped to `{message, type}` — **no stable per-record IDs** —
and lenses cite evidence by verbatim quote. Views + ID-based citations require a shared coordinate
system.

- `build_conversation.py` assigns a **canonical monotonic `turnId`** (sequential index) to each
  record at assembly time. Source `uuid`s are unreliable across merged sessions/sub-agent
  transcripts, so a build-assigned index is the authority. Preserve source `uuid` alongside for
  debugging, but `turnId` is the citation key.
- Every view carries each record's `turnId`. Views are therefore the **same coordinate system**, not
  incompatible ones.

### 4. Self-describing view header (Sensor / anti–Black Box)

Each emitted view file starts with a header record:

```json
{
  "_view": "conversation",
  "_viewVersion": "1.0.0",
  "_sourceTranscriptSha256": "…",
  "_dropped": { "tool_result": 412, "attachment": 17, "file-history-snapshot": 9 },
  "_truncated": { "toolResultTruncLen": 400, "count": 88 },
  "_fullPath": "PACK_DIR/transcript.jsonl"
}
```

- **Dropped block types carry counts**, not just categories — a category list without counts hides
  how much starvation happened (a Black Box with a polite label).
- `_fullPath` lets a lens that detects it's starved say "I couldn't see X" in its output instead of
  silently under-scoring (turns a Silent Fallback into an explicit statement).

### 5. Citation contract (full fix, this PR)

- **Lenses cite evidence by `turnId`** (plus quote for human readability), not by offset.
- **The `eval-pack-evaluator` verifies quotes by `turnId`** against the view it reads.
- The evaluator declares **`activity`**, not `full` — `activity` contains every quotable surface
  (all conversation text + truncated tool evidence). A standing `full` exemption would keep the one
  God reader this design exists to eliminate, capping savings at 8/9.
- **Truncation + verification interaction:** because a lens on `activity` may quote a tool_result
  span that truncation clipped, verification matches the quote against the record's retained span and
  treats a quote that falls entirely inside a truncated region as *unverifiable-due-to-truncation*
  (a distinct, non-penalizing verdict) — never as a hallucination. This is why the full fix is in
  scope now rather than bolted on later.

### 6. Config

- New key **`toolResultTruncLen`** (default e.g. 400), one global limit. **Not** reused from
  `claimTruncLen` — coupling two unrelated tuning domains is Forensic Coding for the future tuner.
- Per-view truncation limits are a knob nobody has asked for; add only on evidence.

### 7. Build mechanics

- Compute the **requested-view set** = union of `inputs.transcript` across the *enabled* lens set
  plus the evaluator. Materialize only those views (never build `activity` if nothing wants it).
- **One sequential pass** over the raw transcript, N sinks emitting all requested views
  simultaneously (Engine — don't re-scan 42 MB per view).
- Each view's per-record projection is a **pure function** (record in → fragment out, no file I/O),
  so the emitter is unit-testable without a transcript on disk (Buffer).
- Runs immediately after `build_conversation.py` assembles the raw transcript, before lens fan-out.

### 8. View versioning

- View versions live in the **projector code** and are emitted into each view header. **Lenses never
  pin a view version** — pinning would force the projector to maintain N historical emitters,
  rebuilding the exact central coupling (Distributed Monolith) that inversion-of-control removes.
- Additive changes bump the header version. Breaking changes ship as a new view name (see §1).

---

## Rollout

1. **This PR:** ship the mechanism (turn IDs, projector, view vocabulary, header, config key,
   ID-based citation + evaluator verification) **and convert exactly one built-in lens** —
   `sycophancy → conversation` (pure-prose, biggest win, gold fixtures exist). Shipping an
   extensibility mechanism with zero internal users is a Paper Tiger: the first exerciser of the path
   would be a third-party stranger hitting bugs we'd have caught.
2. **Follow-ups:** migrate the remaining 7 built-ins one at a time, each gated on a gold-fixture run
   via the lens-evaluator harness.

**Migration rule (procedural Sensor):** changing a lens's view is a **scored** change requiring a
gold-fixture run — never a "pure refactor" commit. Decayed accuracy from a lens quietly starved of a
signal it needed produces no error; the gold set is the only sensor that catches it. Skipping it is a
build failure, not a courtesy.

## Backward compatibility

The 7 unconverted built-ins (and any existing third-party lens) have no `inputs` key → default to
`full` → byte-identical behavior. Zero regression. Turn IDs are additive to the transcript record
shape; the HTML renderer and existing artifacts ignore unknown keys.

## Testing

- **Unit:** per-view pure projection functions (record fixtures → expected fragments); header
  counts; turnId monotonicity across merged sources; truncation boundary (quote inside vs spanning a
  truncated region → correct verdict).
- **Integration:** one-pass emitter over a recorded transcript produces exactly the requested views;
  disabled-lens views are not materialized.
- **Regression:** `sycophancy` on `conversation` matches its gold verdicts (the tracer proves the
  path end-to-end).
- **Cost check:** measure emitted `conversation`/`activity` size vs raw on the 42 MB fixture; record
  the realized reduction.

## Residual risks

1. **Citation drift** — mitigated in-scope by canonical turnIds + ID-based citation + the
   truncation-aware verdict (§3, §5).
2. **Silent semantic starvation on opt-in** — a lens moved to a cheaper view that secretly needed a
   dropped signal just scores slightly worse forever, with no error. Mitigated procedurally by the
   scored-migration rule (gold-fixture run required per view change).

## Explicitly out of scope

- Per-view truncation limits.
- Additional declared artifacts (diff, metrics) — the map-valued frontmatter reserves room; not built
  now.
- Model-summarized (lossy) transcripts — rejected: a model summary silently drops the exact turn a
  lens grades on (Paper Tiger via Silent Fallback). All projections are deterministic.
