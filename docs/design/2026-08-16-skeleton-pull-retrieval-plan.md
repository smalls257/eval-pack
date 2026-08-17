# Skeleton View + Pull-on-Demand — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `skeleton` transcript view (structure + summaries, no bodies) plus a deterministic `pull_turn` tool, so a lens ingests a tiny skeleton and pulls full detail by `turnId` only when needed — cutting tokens past the current 3.9× floor without losing recall.

**Architecture:** `skeleton` is a 4th append-only view produced by the existing projection machinery. It keeps every turn's text, digests `tool_use` inputs, and reduces each `tool_result` to a one-line summary (status + first/last line + size); thinking is dropped. A lens reads the skeleton and calls `pull_turn.py <raw-transcript> <turnId> --field ...` (the model decides when; the tool extracts deterministically). Wired into `generate` and `tune`. Piloted on `verification-rigor`, gated on verdict-consistency (A/B) + measured net savings.

**Tech Stack:** Python 3 stdlib, pytest. Agent-consumed markdown for the two SKILL.md wirings.

## Global Constraints

- **Stdlib only.** No new deps. `python3` (not `python`).
- **Append-only vocabulary:** `full | conversation | activity | skeleton`. `full` stays identity/default. Adding `skeleton` must not change the other three views' output.
- **Recall is structural:** the skeleton MUST contain every turn (with text), every `tool_use` (name + digest), and every `tool_result` (summary with status + size). Pull only affects *depth*.
- **No schema-coupling in lenses:** transcript-JSON knowledge lives only in `transcript_views.py` and `pull_turn.py`. Lenses call `pull_turn` at the domain level, never hand-write jq/grep.
- **Top-level strip still applies:** skeleton records keep only `{turnId, type, message, timestamp}` (reuse the existing `_KEEP_TOP` allowlist).
- **Backward-compat:** unconverted lenses and `full` untouched; `render_html` untouched; a pack whose transcript lacks `turnId` → the lens falls back to reading `RAW_TRANSCRIPT` directly.
- **Two acceptance gates before a lens ships on skeleton:** (1) A/B verdict consistency within LLM variance; (2) measured `skeleton + pulls < current view cost`.

---

## File Structure

- `scripts/transcript_views.py` — **modify.** Add `"skeleton"` to `VIEWS`; add `_digest_tool_use`, `_summarize_tool_result`, and a skeleton branch in `project_record`. Reuse `_KEEP_TOP`.
- `scripts/pull_turn.py` — **create.** Deterministic turn/field extractor + CLI.
- `scripts/build_views.py` — **no change** (already validates against `transcript_views.VIEWS`, so `skeleton` works once added there).
- `scripts/lens_inputs.py` — **no change** (`declared_view` validates against `transcript_views.VIEWS`).
- `skills/generate/SKILL.md` — **modify.** Step 4 dispatch: pass `RAW_TRANSCRIPT` to a skeleton lens.
- `skills/tune/SKILL.md` — **modify.** Build requested views + pass `TRANSCRIPT`/`RAW_TRANSCRIPT` on lens re-dispatch.
- `agents/lenses/verification-rigor.md` — **modify.** Pilot: `inputs.transcript: skeleton` + pull-on-demand body + version bump.
- `agents/lenses/lens-versions.json` — **modify.** Re-lock verification-rigor.
- `scripts/ab_lens.py` — **create.** Repeatable A/B harness (dispatch-agnostic: given two transcript paths, it drives N runs each and diffs). *(See Task 6 note — this is a measurement helper, not a runtime dependency.)*
- `tests/test_transcript_views.py`, `tests/test_pull_turn.py` — **create/modify.**

---

## Task 1: `skeleton` projection in `transcript_views.py`

**Files:**
- Modify: `scripts/transcript_views.py`
- Test: `tests/test_transcript_views.py`

**Interfaces:**
- Produces: `"skeleton"` in `VIEWS`; `project_record(record, "skeleton", tool_result_trunc_len)` returns a record whose `message.content` blocks are: `text` (kept verbatim), `tool_use` → `{type:"tool_use", name, digest, inputBytes}`, `tool_result` → `{type:"tool_result", first, last, bytes, isError}`; `thinking` dropped. Top-level stripped to `_KEEP_TOP`. Empty-projected record → `None`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_transcript_views.py (add)
ASSIST_FULL = {"turnId": 5, "type": "assistant", "toolUseResult": {"x": "y"},
    "message": {"role": "assistant", "content": [
        {"type": "thinking", "thinking": "planning"},
        {"type": "text", "text": "Running the tests now."},
        {"type": "tool_use", "name": "Bash", "input": {"command": "pytest tests/ -q", "description": "run tests"}}]}}
RESULT_REC = {"turnId": 6, "type": "user",
    "message": {"role": "user", "content": [
        {"type": "tool_result", "content": "collecting...\n" + "x"*5000 + "\n3 passed in 1.2s", "is_error": False}]}}

def test_skeleton_keeps_text_digests_tooluse_drops_thinking():
    out = tv.project_record(ASSIST_FULL, "skeleton", 400)
    kinds = [b["type"] for b in out["message"]["content"]]
    assert kinds == ["text", "tool_use"]          # thinking dropped
    tu = out["message"]["content"][1]
    assert tu["name"] == "Bash"
    assert tu["digest"] == "pytest tests/ -q"      # command as digest
    assert "inputBytes" in tu
    assert "toolUseResult" not in out             # top-level stripped
    assert out["turnId"] == 5

def test_skeleton_summarizes_tool_result_no_body():
    out = tv.project_record(RESULT_REC, "skeleton", 400)
    b = out["message"]["content"][0]
    assert b["type"] == "tool_result"
    assert b["last"].strip() == "3 passed in 1.2s"  # last line preserved
    assert b["bytes"] > 5000                          # size recorded
    assert "x"*5000 not in json.dumps(b)              # body NOT included
    assert b["isError"] is False

def test_skeleton_is_a_known_view():
    assert "skeleton" in tv.VIEWS
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_transcript_views.py -k skeleton -v`
Expected: FAIL (`skeleton` not in VIEWS / raises unknown view).

- [ ] **Step 3: Implement**

```python
# scripts/transcript_views.py
VIEWS = ("full", "conversation", "activity", "skeleton")   # append skeleton

_MAX_DIGEST = 200
_MAX_SUMMARY_LINE = 200

def _digest_tool_use(block):
    """tool_use -> name + salient identifier + input size (no full body)."""
    inp = block.get("input")
    ident = ""
    if isinstance(inp, dict):
        for k in ("command", "file_path", "path", "pattern", "url", "query", "prompt"):
            if inp.get(k):
                ident = str(inp[k]); break
    return {"type": "tool_use", "name": block.get("name"),
            "digest": ident[:_MAX_DIGEST],
            "inputBytes": len(_json_len_safe(inp))}

def _summarize_tool_result(block):
    """tool_result -> status + first/last non-empty line + total size (no body)."""
    content = block.get("content")
    text = content if isinstance(content, str) else _json_len_safe(content)
    lines = [ln for ln in text.splitlines() if ln.strip()]
    first = lines[0][:_MAX_SUMMARY_LINE] if lines else ""
    last = lines[-1][:_MAX_SUMMARY_LINE] if len(lines) > 1 else ""
    return {"type": "tool_result", "first": first, "last": last,
            "bytes": len(text), "isError": bool(block.get("is_error", False))}

_SKELETON_BLOCKS = frozenset({"text", "tool_use", "tool_result"})  # thinking excluded
```

Then in `project_record`, before the existing `keep_blocks` logic, branch skeleton:

```python
    if view == "skeleton":
        out = copy.deepcopy(record)
        msg = out.get("message")
        content = msg.get("content") if isinstance(msg, dict) else None
        if isinstance(content, list):
            projected = []
            for block in content:
                if not isinstance(block, dict):
                    continue
                bt = block.get("type")
                if bt == "text":
                    projected.append(block)
                elif bt == "tool_use":
                    projected.append(_digest_tool_use(block))
                elif bt == "tool_result":
                    projected.append(_summarize_tool_result(block))
                # thinking and anything else: dropped
            if not projected:
                return None
            msg["content"] = projected
        # string content (plain user/assistant text) kept as-is
        return {k: v for k, v in out.items() if k in _KEEP_TOP}
```

(Keep the existing `full`/unknown-view/droppable-type checks ahead of this; `skeleton` records still honor `DROPPABLE_TYPES`. Place the skeleton branch after the `DROPPABLE_TYPES` drop and before the conversation/activity block logic.)

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/test_transcript_views.py -v`
Expected: PASS (existing conversation/activity/full tests unchanged — skeleton is a new branch).

- [ ] **Step 5: Commit**

```bash
git add scripts/transcript_views.py tests/test_transcript_views.py
git commit -m "feat(views): skeleton view (text + tool_use digest + tool_result summary, no bodies)"
```

---

## Task 2: `pull_turn.py` deterministic extractor

**Files:**
- Create: `scripts/pull_turn.py`
- Test: `tests/test_pull_turn.py`

**Interfaces:**
- `pull(transcript_path, turn_id, field=None) -> str` — returns the full body of the turn: `field=None` → the whole record as JSON; `text`/`thinking` → concatenated blocks of that type; `tool_input` → the tool_use input(s) as JSON; `tool_result` → the full untruncated tool_result content(s). Raises `KeyError` if `turn_id` absent.
- CLI: `pull_turn.py <transcript> <turnId> [--field text|thinking|tool_input|tool_result]` → prints the body; unknown turnId → stderr + exit 2.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_pull_turn.py
import json, subprocess, sys
from pathlib import Path
SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import pull_turn

def _t(tmp_path):
    p = tmp_path / "transcript.jsonl"
    p.write_text(
        '{"turnId":5,"type":"assistant","message":{"role":"assistant","content":['
        '{"type":"thinking","thinking":"secret plan"},'
        '{"type":"text","text":"done"},'
        '{"type":"tool_use","name":"Bash","input":{"command":"pytest"}}]}}\n'
        '{"turnId":6,"type":"user","message":{"role":"user","content":['
        '{"type":"tool_result","content":"FULL LOG line1\\n...5000 chars...\\nFAILED"}]}}\n',
        encoding="utf-8")
    return p

def test_pull_tool_result_returns_full_body(tmp_path):
    p = _t(tmp_path)
    assert "FULL LOG line1" in pull_turn.pull(p, 6, field="tool_result")
    assert "FAILED" in pull_turn.pull(p, 6, field="tool_result")

def test_pull_thinking_and_text(tmp_path):
    p = _t(tmp_path)
    assert "secret plan" in pull_turn.pull(p, 5, field="thinking")
    assert "done" in pull_turn.pull(p, 5, field="text")

def test_unknown_turn_raises(tmp_path):
    p = _t(tmp_path)
    import pytest
    with pytest.raises(KeyError):
        pull_turn.pull(p, 99, field="text")

def test_cli_unknown_turn_exits_2(tmp_path):
    p = _t(tmp_path)
    r = subprocess.run([sys.executable, str(SCRIPTS/"pull_turn.py"), str(p), "99", "--field", "text"],
                       capture_output=True, text=True)
    assert r.returncode == 2 and r.stderr.strip()

def test_cli_prints_body(tmp_path):
    p = _t(tmp_path)
    r = subprocess.run([sys.executable, str(SCRIPTS/"pull_turn.py"), str(p), "6", "--field", "tool_result"],
                       capture_output=True, text=True)
    assert r.returncode == 0 and "FAILED" in r.stdout
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_pull_turn.py -v`
Expected: FAIL (`ModuleNotFoundError: pull_turn`).

- [ ] **Step 3: Implement**

```python
#!/usr/bin/env python3
# scripts/pull_turn.py
"""Deterministically pull one turn's full body from a raw transcript, by turnId.

The single place that knows the transcript's JSON shape for on-demand retrieval — a
skeleton-view lens calls this instead of hand-writing jq/grep. Field selectors return the
full, UNtruncated content the skeleton summarized."""
import argparse
import json
import sys
from pathlib import Path

_FIELD_BLOCK = {"text": "text", "thinking": "thinking",
                "tool_input": "tool_use", "tool_result": "tool_result"}


def _record(transcript_path, turn_id):
    with open(transcript_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            if o.get("_view"):
                continue
            if o.get("turnId") == turn_id:
                return o
    raise KeyError("turnId {} not found in {}".format(turn_id, transcript_path))


def pull(transcript_path, turn_id, field=None):
    o = _record(transcript_path, turn_id)
    if field is None:
        return json.dumps(o)
    block_type = _FIELD_BLOCK.get(field)
    if block_type is None:
        raise ValueError("unknown field {!r}".format(field))
    msg = o.get("message") or {}
    content = msg.get("content")
    if isinstance(content, str):
        return content if field == "text" else ""
    parts = []
    for b in (content or []):
        if not isinstance(b, dict) or b.get("type") != block_type:
            continue
        if block_type == "text":
            parts.append(b.get("text", ""))
        elif block_type == "thinking":
            parts.append(b.get("thinking", ""))
        elif block_type == "tool_use":
            parts.append(json.dumps(b.get("input", "")))
        elif block_type == "tool_result":
            c = b.get("content")
            parts.append(c if isinstance(c, str) else json.dumps(c))
    return "\n".join(parts)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Pull a turn's full body by turnId")
    ap.add_argument("transcript", type=Path)
    ap.add_argument("turn_id", type=int)
    ap.add_argument("--field", choices=sorted(_FIELD_BLOCK))
    args = ap.parse_args(argv)
    try:
        sys.stdout.write(pull(args.transcript, args.turn_id, field=args.field))
        return 0
    except KeyError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/test_pull_turn.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/pull_turn.py tests/test_pull_turn.py
git commit -m "feat(views): pull_turn.py — deterministic by-turnId body retrieval"
```

---

## Task 3: Dispatch a skeleton lens with `RAW_TRANSCRIPT` (`generate`)

**Files:**
- Modify: `skills/generate/SKILL.md` (Step 4)
- Test: manual reading + full suite (agent-consumed markdown; no unit test)

**Interfaces:**
- Consumes: `requested_views` (already builds `skeleton` when a lens declares it — no code change), the per-lens `TRANSCRIPT` resolution (Task 8 of the prior plan).
- Produces: a lens whose declared view is `skeleton` is dispatched with `TRANSCRIPT = ${ABS_PACK_DIR}/views/skeleton.jsonl` AND `RAW_TRANSCRIPT = ${ABS_PACK_DIR}/transcript.jsonl`.

- [ ] **Step 1: Extend the per-lens TRANSCRIPT resolution**

In Step 4, where the per-lens `TRANSCRIPT` path is resolved, add: "If the lens's declared view is `skeleton`, also pass `RAW_TRANSCRIPT = ${ABS_PACK_DIR}/transcript.jsonl` — the pull source. For non-skeleton lenses, omit it."

- [ ] **Step 2: Extend the dispatch prompt template**

Change the dispatch template so a skeleton lens's prompt includes:
> TRANSCRIPT is `${ABS_PACK_DIR}/views/skeleton.jsonl` (a skeleton — every turn's text, tool-call digests, and one-line result summaries; no bodies). RAW_TRANSCRIPT is `${ABS_PACK_DIR}/transcript.jsonl`. To read a turn's full body, run `"$PYTHON" "${CLAUDE_PLUGIN_ROOT}/scripts/pull_turn.py" "$RAW_TRANSCRIPT" <turnId> --field <text|thinking|tool_input|tool_result>`. Pull selectively.

- [ ] **Step 3: Verify + full suite**

Run: `python3 -m pytest tests/ -q` (should stay green — markdown-only change).
Read the Step 4 diff and confirm non-skeleton lenses are unaffected (they still get only `TRANSCRIPT`).

- [ ] **Step 4: Commit**

```bash
git add skills/generate/SKILL.md
git commit -m "feat(generate): hand skeleton lenses RAW_TRANSCRIPT + the pull_turn recipe"
```

---

## Task 4: Wire `tune` for views + pull

**Files:**
- Modify: `skills/tune/SKILL.md`
- Test: manual reading + full suite

**Interfaces:**
- Produces: `tune`'s single-lens re-dispatch (and the batch path) builds the requested views (incl. skeleton) and passes `TRANSCRIPT` (declared view) + `RAW_TRANSCRIPT` (for skeleton), mirroring `generate` Step 4. Falls back cleanly when the stored transcript lacks `turnId` (lens reads `RAW_TRANSCRIPT` directly).

- [ ] **Step 1: Add the view-build step to tune**

Before tune re-dispatches a lens, insert the same view-build block `generate` uses (compute `requested_views` via `lens_inputs.py`, run `build_views.py` guarded by `[ -n "$VIEWS" ]`, with `--tool-result-trunc-len` from config).

- [ ] **Step 2: Pass the transcript paths on re-dispatch**

In tune's lens re-dispatch (the section that currently passes `PACK_DIR`/`REPO_ROOT`/`DIFF_BASE`), add per-lens `TRANSCRIPT` resolution (declared view → path; `full`/none → `transcript.jsonl`) and `RAW_TRANSCRIPT` for skeleton lenses — copy the wording from `generate` Step 4 / the dispatch template.

- [ ] **Step 3: Fallback note**

Add: "If `${PACK_DIR}/transcript.jsonl` lacks `turnId` (a pack built before the turnId change), a skeleton lens cannot pull by turnId — pass its `TRANSCRIPT` as the raw `transcript.jsonl` so it reads the full transcript directly. Look-back never breaks." (Detect by checking the first data record for a `turnId` key, or simply document the degraded path.)

- [ ] **Step 4: Verify + full suite**

Run: `python3 -m pytest tests/ -q` (green — markdown change). Read the diff; confirm the non-skeleton re-eval path is unchanged from today for lenses on `full`.

- [ ] **Step 5: Commit**

```bash
git add skills/tune/SKILL.md
git commit -m "feat(tune): build views + pass TRANSCRIPT/RAW_TRANSCRIPT so re-eval gets the savings"
```

---

## Task 5: Convert `verification-rigor` to skeleton (pilot)

**Files:**
- Modify: `agents/lenses/verification-rigor.md`, `agents/lenses/lens-versions.json`
- Test: `python3 -m pytest tests/test_lens_versions.py tests/test_graded_lens_contracts.py -v`; full suite

**Interfaces:**
- Produces: `verification-rigor` declares `inputs.transcript: skeleton`; its body reads the skeleton and pulls tool_results by turnId as needed; output contract/schema unchanged.

- [ ] **Step 1: Frontmatter**

Change `inputs.transcript` from `activity` to `skeleton` in `agents/lenses/verification-rigor.md`.

- [ ] **Step 2: Body — skeleton + pull instructions**

Replace step 1 of its body (the "read the transcript" bullet) with skeleton-aware wording:
> Read the **skeleton** at `TRANSCRIPT`: every turn's text, tool-call digests, and one-line result summaries (status + first/last line + size) — no bodies. For each success claim, the result summary usually shows whether a backing command ran and how it ended. When a summary is ambiguous, or you must quote the evidence, pull that turn's full result: `"$PYTHON" "$CLAUDE_PLUGIN_ROOT/scripts/pull_turn.py" "$RAW_TRANSCRIPT" <turnId> --field tool_result`. Pull selectively — most claims resolve from the summary. If no `TRANSCRIPT`/`RAW_TRANSCRIPT` was given, read `PACK_DIR/transcript.jsonl` directly.

Do NOT change its output-contract JSON block or schema.

- [ ] **Step 3: Re-lock version**

Bump `verification-rigor` patch digit in `lens-versions.json` (currently `1.0.2` → `1.0.3`) and update its sha256:
`python3 -c "import sys; sys.path.insert(0,'scripts'); import lens_versions; print(lens_versions.hash_file('agents/lenses/verification-rigor.md'))"`

- [ ] **Step 4: Verify**

Run: `python3 -m pytest tests/test_lens_versions.py tests/test_graded_lens_contracts.py -q` (must pass — verification-rigor has no gold bundle, so this checks lock + contract integrity). Then full suite `python3 -m pytest tests/ -q`.
If `tests/test_assemble_lenses.py` pins verification-rigor's old version, update the assertion to the new version (as was done for the 7-lens conversion).

- [ ] **Step 5: Commit**

```bash
git add agents/lenses/verification-rigor.md agents/lenses/lens-versions.json tests/test_assemble_lenses.py
git commit -m "feat(verification-rigor): read the skeleton, pull tool_results on demand (pilot)"
```

---

## Task 6: Acceptance — A/B verdict consistency + net-savings measurement

**Files:**
- Create: `scripts/ab_lens.py` (measurement helper; not a runtime dependency)
- Test: run the gates; record numbers in the PR body.

**Interfaces:**
- `ab_lens.py` builds the two inputs (skeleton + raw) for a chosen pack, and prints the byte/token sizes of each so net-savings is computable. The *verdict* A/B is run by dispatching the lens both ways (skeleton+pull vs full) — this is a controller/agent step, documented here, not automated in-script (it needs live model dispatch).

- [ ] **Step 1: Build the measurement helper**

```python
#!/usr/bin/env python3
# scripts/ab_lens.py
"""Prep + size an A/B for a skeleton lens: build skeleton + report ingest sizes.
The verdict comparison is run by dispatching the lens against each transcript path this prints."""
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_views  # noqa

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("transcript", type=Path)   # raw full transcript.jsonl (has turnId)
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--tool-result-trunc-len", type=int, default=400)
    args = ap.parse_args(argv)
    build_views.main([str(args.transcript), str(args.out_dir), "skeleton",
                      "--tool-result-trunc-len", str(args.tool_result_trunc_len)])
    raw = args.transcript.stat().st_size
    skel = (args.out_dir / "skeleton.jsonl").stat().st_size
    print("FULL  bytes={:,}  ~tokens={:,}".format(raw, raw//4))
    print("SKEL  bytes={:,}  ~tokens={:,}  ({:.1f}x smaller)".format(skel, skel//4, raw/skel))
    print("A/B: dispatch verification-rigor twice —")
    print("  full:     TRANSCRIPT={}".format(args.transcript))
    print("  skeleton: TRANSCRIPT={}/skeleton.jsonl  RAW_TRANSCRIPT={}".format(args.out_dir, args.transcript))
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Gate 1 — verdict consistency (A/B)**

On the `report` pack (the one used for the activity A/B), dispatch `verification-rigor` twice per side (full-read × 2, skeleton+pull × 2) following the protocol already used: same model, compare `score` band and the `proven`/`unproven` sets. Skeleton runs sum the pull-tool output they fetched.
**Pass criterion:** skeleton verdict band and core `proven`/`unproven` match full-read within the within-side variance (as measured: full activity A/B varied ~4 points).

- [ ] **Step 3: Gate 2 — net savings**

For each skeleton run, net ingest = skeleton size + sum of pulled bodies. Compute realized net vs the full-read ingest and vs the current activity ingest.
**Pass criterion:** `skeleton + pulls < activity` ingest on the test session. Record the realized number.

- [ ] **Step 4: Decide**

If both gates pass → verification-rigor ships on skeleton; note the numbers in the PR body. If Gate 1 fails → keep verification-rigor on `activity`, record the failure mode (which claim needed a body the model didn't pull), and revisit the skeleton summary shape (e.g. include exit code) before retrying. If Gate 2 fails (over-pulling) → tighten the pull guidance and re-measure.

- [ ] **Step 5: Commit**

```bash
git add scripts/ab_lens.py
git commit -m "test(views): A/B prep helper for skeleton acceptance gates"
```

---

## Self-Review

- **Spec coverage:** skeleton view + shape (Task 1), thinking dropped (Task 1), pull_turn deterministic tool (Task 2), model-decides/tool-extracts (Tasks 2/5), generate wiring + RAW_TRANSCRIPT (Task 3), tune wiring + fallback (Task 4), pilot verification-rigor (Task 5), both acceptance gates (Task 6), recall-structural (Task 1 keeps every turn/call/result-summary), append-only vocab + backward-compat (Task 1 leaves other views untouched; `full` default). Rollout beyond the pilot = follow-ups (out of this plan, per spec).
- **Placeholder scan:** none — real code in every code step. Task 3/4 are markdown edits with exact wording specified.
- **Type consistency:** `project_record(record, view, tool_result_trunc_len)` (skeleton branch), `_digest_tool_use`/`_summarize_tool_result`, `VIEWS` gains `"skeleton"`, `pull(transcript_path, turn_id, field=None)`, CLI `pull_turn.py <transcript> <turnId> --field ...` — used consistently across Tasks 1, 2, 3, 5, 6.

## Out of scope (deliberate)

- Converting the other `activity`/`conversation` lenses to skeleton (staged follow-ups, each gated on the two acceptance checks).
- Automating the verdict A/B end-to-end (needs live model dispatch; run as a controller step).
- Lens-declared grep recipes (rejected in the spec).
