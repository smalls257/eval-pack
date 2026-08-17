# Transcript Projections — Plan 1: Projection Mechanism (Implementation Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic, lens-blind transcript-projection layer so each lens reads a condensed view it declares in frontmatter instead of the full multi-MB transcript.

**Architecture:** After the raw transcript is assembled, a pure-function projector emits only the views the enabled lens set requests (`full`/`conversation`/`activity`), each carrying build-assigned canonical `turnId`s and a self-describing header. The dispatcher resolves each lens's declared view to a concrete file path and hands it in as `TRANSCRIPT`. Default (no declaration) = the full transcript = byte-identical to today.

**Tech Stack:** Python 3 stdlib only (no PyYAML, no deps), pytest. Node test files exist but are untouched here.

## Global Constraints

- **Stdlib only.** No new Python dependencies. Frontmatter parsing is regex-based, not PyYAML. (Matches `merge_sessions.py`, `config.py`, `lens_manifest.py`.)
- **Zero regression by default.** A lens with no `inputs` key resolves to `full` → reads the existing `transcript.jsonl` → identical behavior. This is the safety property; every task must preserve it.
- **View vocabulary is exactly `full` | `conversation` | `activity`** and append-only. No thinking on/off axis.
- **Truncation limit key is `toolResultTruncLen`** (new), one global int, default `400`. Never reuse `claimTruncLen`.
- **Deterministic, no model calls.** The projector is pure Python over JSONL. No summarization.
- **Config precedence unchanged:** `DEFAULTS < extends < .eval-pack.json < .eval-pack.local.json < CLAUDE_PLUGIN_OPTION_*` (`config.py`).
- Plan 2 (ID-based citation, evaluator→`activity`) is a separate plan on this branch. This plan STOPS at emitting `turnId` into views + headers; it does NOT change the evidence-resolution gate or the evaluator's view. `sycophancy` here is converted to read `conversation` but keeps its current quote-based citation (safe: `conversation` preserves assistant text verbatim).

---

## File Structure

- `scripts/merge_sessions.py` — **modify.** Assign a canonical monotonic `turnId` to every merged record.
- `scripts/transcript_views.py` — **create.** Pure per-record projection functions + view emitter + header builder. One responsibility: turn a raw record stream into named view fragments.
- `scripts/build_views.py` — **create.** Thin CLI wrapper: read a raw transcript + a requested-view set, write `PACK_DIR/views/<view>.jsonl`. (Mirrors the `merge_sessions` script/`build_conversation` CLI split — logic in a lib, I/O in a CLI.)
- `scripts/lens_inputs.py` — **create.** Parse a lens `.md`'s frontmatter `inputs.transcript` (regex, stdlib) → view name, defaulting to `full`; and resolve the requested-view set for a config's lens list.
- `scripts/config.py` — **modify.** Add `toolResultTruncLen` to DEFAULTS, `_TYPES`, and `validate()`.
- `agents/lenses/sycophancy.md` — **modify.** Add `inputs.transcript: conversation` frontmatter; body reads the handed-in `TRANSCRIPT` path instead of a hardcoded one.
- `skills/generate/SKILL.md` — **modify.** Step 4: build requested views after transcript assembly; pass each lens a `TRANSCRIPT` path resolved from its declared view.
- `tests/test_transcript_views.py` — **create.**
- `tests/test_lens_inputs.py` — **create.**
- `tests/test_merge_sessions.py` — **modify** (add turnId cases).
- `tests/test_config.py` — **modify** (add toolResultTruncLen validation cases).

---

## Task 1: Canonical turnId in the merged transcript

**Files:**
- Modify: `scripts/merge_sessions.py` (`merge()`, after the sort)
- Test: `tests/test_merge_sessions.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: every record emitted by `merge()` / `write_merged()` now carries an integer `turnId` (0-based, monotonic in final sorted order). Source `uuid` is left untouched. This is the citation coordinate system Plan 2 builds on.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_merge_sessions.py (add)
import merge_sessions

def test_merge_assigns_monotonic_turnid(tmp_path):
    p = tmp_path / "s.jsonl"
    p.write_text(
        '{"uuid":"b","timestamp":"2026-01-01T00:00:02Z","type":"assistant"}\n'
        '{"uuid":"a","timestamp":"2026-01-01T00:00:01Z","type":"user"}\n',
        encoding="utf-8",
    )
    entries = merge_sessions.merge([p])
    # sorted by timestamp: a then b
    assert [e["turnId"] for e in entries] == [0, 1]
    assert [e["uuid"] for e in entries] == ["a", "b"]

def test_turnid_is_assigned_after_sort_even_without_timestamps(tmp_path):
    p = tmp_path / "s.jsonl"
    p.write_text(
        '{"uuid":"x","type":"user"}\n{"uuid":"y","type":"assistant"}\n',
        encoding="utf-8",
    )
    entries = merge_sessions.merge([p])
    assert [e["turnId"] for e in entries] == [0, 1]
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_merge_sessions.py -k turnid -v`
Expected: FAIL (`KeyError: 'turnId'`).

- [ ] **Step 3: Implement**

```python
# scripts/merge_sessions.py — in merge(), replace the final two lines
def merge(paths):
    """Return merged, deduped, time-ordered entries, each stamped with a monotonic turnId."""
    seen = set()
    entries = []
    for path in paths:
        for entry in _load(path):
            uid = entry.get("uuid")
            if uid is not None:
                if uid in seen:
                    continue
                seen.add(uid)
            entries.append(entry)
    entries.sort(key=lambda e: e.get("timestamp") or "")
    for i, e in enumerate(entries):
        e["turnId"] = i  # canonical citation coordinate: assigned after ordering, not from source
    return entries
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_merge_sessions.py -v`
Expected: PASS (existing tests still green — `turnId` is additive).

- [ ] **Step 5: Commit**

```bash
git add scripts/merge_sessions.py tests/test_merge_sessions.py
git commit -m "feat(transcript): assign canonical turnId to merged records"
```

---

## Task 2: Pure per-record view projection functions

**Files:**
- Create: `scripts/transcript_views.py`
- Test: `tests/test_transcript_views.py`

**Interfaces:**
- Consumes: raw merged records (dicts with `turnId`, `type`, `message`).
- Produces:
  - `VIEWS = ("full", "conversation", "activity")`
  - `project_record(record, view, tool_result_trunc_len) -> dict | None` — returns the projected record (keeps `turnId`), or `None` if the record is dropped from that view.
  - `DROPPABLE_TYPES` — top-level record `type`s dropped by non-full views.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_transcript_views.py
import transcript_views as tv

USER_TEXT = {"turnId": 0, "type": "user",
             "message": {"role": "user", "content": [{"type": "text", "text": "hi"}]}}
ASSISTANT = {"turnId": 1, "type": "assistant",
             "message": {"role": "assistant", "content": [
                 {"type": "thinking", "thinking": "hmm"},
                 {"type": "text", "text": "hello"},
                 {"type": "tool_use", "name": "Bash", "input": {"command": "pytest"}}]}}
TOOL_RESULT = {"turnId": 2, "type": "user",
               "message": {"role": "user", "content": [
                   {"type": "tool_result", "content": "X" * 5000}]}}
NOISE = {"turnId": 3, "type": "file-history-snapshot", "message": {}}

def test_full_is_identity():
    assert tv.project_record(ASSISTANT, "full", 400) == ASSISTANT

def test_conversation_keeps_text_and_thinking_drops_tools():
    out = tv.project_record(ASSISTANT, "conversation", 400)
    kinds = [b["type"] for b in out["message"]["content"]]
    assert kinds == ["thinking", "text"]  # tool_use removed
    assert out["turnId"] == 1

def test_conversation_drops_tool_result_record():
    assert tv.project_record(TOOL_RESULT, "conversation", 400) is None

def test_conversation_drops_structural_noise():
    assert tv.project_record(NOISE, "conversation", 400) is None

def test_activity_keeps_tool_use_and_truncates_tool_result():
    au = tv.project_record(ASSISTANT, "activity", 400)
    assert [b["type"] for b in au["message"]["content"]] == ["thinking", "text", "tool_use"]
    tr = tv.project_record(TOOL_RESULT, "activity", 400)
    block = tr["message"]["content"][0]
    assert block["type"] == "tool_result"
    assert len(block["content"]) < 5000
    assert block.get("_truncated") is True

def test_activity_drops_structural_noise():
    assert tv.project_record(NOISE, "activity", 400) is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_transcript_views.py -v`
Expected: FAIL (`ModuleNotFoundError: transcript_views`).

- [ ] **Step 3: Implement**

```python
# scripts/transcript_views.py
"""Deterministic transcript projections. Pure functions: record in -> fragment out, no I/O.

Views (append-only vocabulary):
  full          - identity; the raw record unchanged.
  conversation  - real user + assistant text + thinking. No tool payloads, no structural noise.
  activity      - conversation + tool_use (name/input) + truncated tool_result + exit codes.
"""
import copy

VIEWS = ("full", "conversation", "activity")

# Top-level record types that are pure structure/noise — dropped by every non-full view.
DROPPABLE_TYPES = frozenset({
    "file-history-snapshot", "file-history-delta", "queue-operation",
    "attachment", "ai-title", "last-prompt", "mode", "pr-link", "system",
})

# Content-block types kept by each non-full view.
_CONVERSATION_BLOCKS = frozenset({"text", "thinking"})
_ACTIVITY_BLOCKS = frozenset({"text", "thinking", "tool_use", "tool_result"})


def _truncate_tool_result(block, limit):
    b = copy.deepcopy(block)
    content = b.get("content")
    text = content if isinstance(content, str) else _json_len_safe(content)
    if isinstance(text, str) and len(text) > limit:
        head = limit // 2
        tail = limit - head
        b["content"] = text[:head] + "\n…[truncated]…\n" + text[-tail:]
        b["_truncated"] = True
    return b


def _json_len_safe(content):
    import json
    try:
        return json.dumps(content)
    except (TypeError, ValueError):
        return str(content)


def project_record(record, view, tool_result_trunc_len):
    """Project one raw record into `view`. Returns the projected dict, or None if dropped.

    `turnId` is always preserved on a kept record (the citation coordinate)."""
    if view == "full":
        return record
    if record.get("type") in DROPPABLE_TYPES:
        return None

    keep_blocks = _CONVERSATION_BLOCKS if view == "conversation" else _ACTIVITY_BLOCKS
    out = copy.deepcopy(record)
    msg = out.get("message")
    content = msg.get("content") if isinstance(msg, dict) else None

    if isinstance(content, list):
        projected = []
        for block in content:
            if not isinstance(block, dict):
                continue
            bt = block.get("type")
            if bt not in keep_blocks:
                continue
            if bt == "tool_result":
                projected.append(_truncate_tool_result(block, tool_result_trunc_len))
            else:
                projected.append(block)
        # A record whose blocks are ALL dropped (e.g. a tool_result record under conversation)
        # carries no signal for this view — drop the record entirely.
        if not projected:
            return None
        msg["content"] = projected
    elif isinstance(content, str):
        pass  # string content is conversational text; keep as-is
    return out
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_transcript_views.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/transcript_views.py tests/test_transcript_views.py
git commit -m "feat(views): pure per-record transcript projection functions"
```

---

## Task 3: View emitter + self-describing header

**Files:**
- Modify: `scripts/transcript_views.py` (add `emit_views`)
- Test: `tests/test_transcript_views.py` (add)

**Interfaces:**
- Consumes: `project_record` (Task 2).
- Produces: `emit_views(records, views, out_dir, tool_result_trunc_len, source_sha256) -> dict[view -> path]`. Each output file's FIRST line is a header record; subsequent lines are projected records. Header shape:
  `{"_view", "_viewVersion", "_sourceTranscriptSha256", "_dropped": {type: count}, "_truncated": {"toolResultTruncLen": int, "count": int}, "_fullPath": str}`.
- `VIEW_VERSION = "1.0.0"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_transcript_views.py (add)
import json
import transcript_views as tv

def _records():
    return [
        {"turnId": 0, "type": "user", "message": {"role": "user", "content": [{"type": "text", "text": "hi"}]}},
        {"turnId": 1, "type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "content": "Z" * 900}]}},
        {"turnId": 2, "type": "file-history-snapshot", "message": {}},
    ]

def test_emit_writes_header_then_records(tmp_path):
    paths = tv.emit_views(_records(), ["conversation"], tmp_path, 400, "abc123")
    lines = paths["conversation"].read_text().splitlines()
    header = json.loads(lines[0])
    assert header["_view"] == "conversation"
    assert header["_viewVersion"] == tv.VIEW_VERSION
    assert header["_sourceTranscriptSha256"] == "abc123"
    # tool_result record + noise record dropped -> counts recorded
    assert header["_dropped"]["file-history-snapshot"] == 1
    assert header["_dropped"]["tool_result"] == 1  # a whole record dropped for having only tool_result
    body = [json.loads(x) for x in lines[1:]]
    assert [r["turnId"] for r in body] == [0]

def test_emit_activity_records_truncation_count(tmp_path):
    paths = tv.emit_views(_records(), ["activity"], tmp_path, 400, "abc123")
    header = json.loads(paths["activity"].read_text().splitlines()[0])
    assert header["_truncated"] == {"toolResultTruncLen": 400, "count": 1}
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_transcript_views.py -k emit -v`
Expected: FAIL (`AttributeError: emit_views`).

- [ ] **Step 3: Implement**

```python
# scripts/transcript_views.py (add)
import json as _json
from pathlib import Path

VIEW_VERSION = "1.0.0"


def _dropped_reason(record, view):
    """Why a record was dropped from a non-full view — a type label for the header counts."""
    t = record.get("type")
    if t in DROPPABLE_TYPES:
        return t
    # dropped because every content block was filtered out — label by the blocks it held
    msg = record.get("message") or {}
    content = msg.get("content")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type"):
                return block["type"]
    return "empty"


def emit_views(records, views, out_dir, tool_result_trunc_len, source_sha256):
    """Project `records` into each requested view and write one JSONL per view. Returns {view: Path}.
    The full view is a straight copy (header still prepended for provenance)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    result = {}
    for view in views:
        dropped, trunc_count, body = {}, 0, []
        for rec in records:
            projected = project_record(rec, view, tool_result_trunc_len)
            if projected is None:
                key = _dropped_reason(rec, view)
                dropped[key] = dropped.get(key, 0) + 1
                continue
            if view == "activity":
                for b in (projected.get("message", {}).get("content") or []):
                    if isinstance(b, dict) and b.get("_truncated"):
                        trunc_count += 1
            body.append(projected)
        header = {
            "_view": view,
            "_viewVersion": VIEW_VERSION,
            "_sourceTranscriptSha256": source_sha256,
            "_dropped": dropped,
            "_truncated": {"toolResultTruncLen": tool_result_trunc_len, "count": trunc_count},
            "_fullPath": str(out_dir.parent / "transcript.jsonl"),
        }
        path = out_dir / (view + ".jsonl")
        with open(path, "w", encoding="utf-8") as f:
            f.write(_json.dumps(header) + "\n")
            for rec in body:
                f.write(_json.dumps(rec) + "\n")
        result[view] = path
    return result
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_transcript_views.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/transcript_views.py tests/test_transcript_views.py
git commit -m "feat(views): view emitter with self-describing header + drop/truncation counts"
```

---

## Task 4: `toolResultTruncLen` config key

**Files:**
- Modify: `scripts/config.py` (DEFAULTS, `_TYPES`, `validate()`)
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: nothing.
- Produces: resolved config carries `toolResultTruncLen: int` (default 400); a negative value is a validation error.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py (add)
import config

def test_tool_result_trunc_len_default():
    assert config.read_config()["toolResultTruncLen"] == 400

def test_tool_result_trunc_len_negative_rejected():
    errors = config.validate({**config.DEFAULTS, "toolResultTruncLen": -1})
    assert any("toolResultTruncLen" in e for e in errors)

def test_tool_result_trunc_len_wrong_type_rejected():
    errors = config.validate({**config.DEFAULTS, "toolResultTruncLen": "big"})
    assert any("toolResultTruncLen" in e for e in errors)
```

(If `validate()` isn't the exact public name/shape, match the existing pattern used by the `skillArgsMaxLen` non-negative check already in `config.py` around the "Non-negative bound" comment.)

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_config.py -k tool_result -v`
Expected: FAIL (default missing / no validation).

- [ ] **Step 3: Implement**

In `scripts/config.py`:
- Add to `DEFAULTS` (near `claimTruncLen`):
  ```python
      # Truncation length for tool_result payloads in the `activity` transcript view.
      "toolResultTruncLen": 400,
  ```
- Add to `_TYPES`:
  ```python
      "toolResultTruncLen": int,
  ```
- In `validate()`, beside the existing `skillArgsMaxLen` non-negative check, add:
  ```python
      m = cfg.get("toolResultTruncLen")
      if isinstance(m, int) and not isinstance(m, bool) and m < 0:
          errors.append("toolResultTruncLen: must be >= 0, got {}".format(m))
  ```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/config.py tests/test_config.py
git commit -m "feat(config): add toolResultTruncLen (activity-view tool_result cap)"
```

---

## Task 5: Resolve a lens's declared view from frontmatter

**Files:**
- Create: `scripts/lens_inputs.py`
- Test: `tests/test_lens_inputs.py`

**Interfaces:**
- Consumes: a lens `.md`'s text; `transcript_views.VIEWS`.
- Produces:
  - `declared_view(md_text) -> str` — the `inputs.transcript` value if present and valid, else `"full"`. Unknown view string → `"full"` (fail-safe, never raises).
  - `requested_views(lens_dir, lens_skills) -> set[str]` — union of declared views across the given skills (a skill whose `.md` is absent → `"full"`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_lens_inputs.py
import lens_inputs

FLOW = "inputs:\n  transcript: conversation\n"
INLINE = "inputs: { transcript: activity }\n"

def _md(front):
    return "---\nname: x\ntools: Read\n{}---\n\nbody\n".format(front)

def test_declared_view_block_form():
    assert lens_inputs.declared_view(_md(FLOW)) == "conversation"

def test_declared_view_inline_form():
    assert lens_inputs.declared_view(_md(INLINE)) == "activity"

def test_missing_inputs_defaults_to_full():
    assert lens_inputs.declared_view(_md("")) == "full"

def test_unknown_view_falls_back_to_full():
    assert lens_inputs.declared_view(_md("inputs:\n  transcript: bogus\n")) == "full"

def test_requested_views_unions_and_defaults(tmp_path):
    (tmp_path / "a.md").write_text(_md(FLOW), encoding="utf-8")
    (tmp_path / "b.md").write_text(_md(INLINE), encoding="utf-8")
    # 'c' has no file -> full
    assert lens_inputs.requested_views(tmp_path, ["a", "b", "c"]) == {"conversation", "activity", "full"}
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_lens_inputs.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

```python
# scripts/lens_inputs.py
"""Resolve a lens's declared transcript view from its .md frontmatter. Stdlib regex only.

A lens declares, in YAML frontmatter:  inputs: { transcript: conversation }
or the block form:                     inputs:
                                         transcript: conversation
Absent / unknown -> "full" (fail-safe: a lens is never silently starved)."""
import re
from pathlib import Path

import transcript_views

_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
# matches `transcript: <word>` on its own line (block form) OR inside `inputs: { transcript: <word> }`
_TRANSCRIPT = re.compile(r"transcript\s*:\s*([A-Za-z0-9_-]+)")
_INPUTS_PRESENT = re.compile(r"^\s*inputs\s*:", re.MULTILINE)


def declared_view(md_text):
    m = _FRONTMATTER.search(md_text or "")
    if not m:
        return "full"
    front = m.group(1)
    if not _INPUTS_PRESENT.search(front):
        return "full"
    t = _TRANSCRIPT.search(front)
    if not t:
        return "full"
    view = t.group(1)
    return view if view in transcript_views.VIEWS else "full"


def requested_views(lens_dir, lens_skills):
    lens_dir = Path(lens_dir)
    views = set()
    for skill in lens_skills:
        md = lens_dir / (skill + ".md")
        if md.is_file():
            views.add(declared_view(md.read_text(encoding="utf-8")))
        else:
            views.add("full")
    return views
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_lens_inputs.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/lens_inputs.py tests/test_lens_inputs.py
git commit -m "feat(views): resolve a lens's declared transcript view from frontmatter"
```

---

## Task 6: `build_views.py` CLI

**Files:**
- Create: `scripts/build_views.py`
- Test: `tests/test_transcript_views.py` (add an end-to-end CLI case) or a small `tests/test_build_views.py`

**Interfaces:**
- Consumes: `transcript_views.emit_views`, `lens_inputs` not needed here (view set is passed in).
- Produces: CLI `build_views.py <transcript.jsonl> <out_dir> <view>[ <view>...]` → writes `<out_dir>/<view>.jsonl` for each. Computes the source sha256 itself. Reads records via `merge_sessions._load`-style line parsing (reuse, don't duplicate).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_build_views.py
import json, subprocess, sys, hashlib
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"

def test_cli_emits_requested_views(tmp_path):
    t = tmp_path / "transcript.jsonl"
    t.write_text(
        '{"turnId":0,"type":"user","message":{"role":"user","content":[{"type":"text","text":"hi"}]}}\n'
        '{"turnId":1,"type":"file-history-snapshot","message":{}}\n',
        encoding="utf-8",
    )
    out = tmp_path / "views"
    r = subprocess.run([sys.executable, str(SCRIPTS / "build_views.py"), str(t), str(out),
                        "conversation", "activity"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    conv = (out / "conversation.jsonl").read_text().splitlines()
    header = json.loads(conv[0])
    assert header["_view"] == "conversation"
    assert header["_sourceTranscriptSha256"] == hashlib.sha256(t.read_bytes()).hexdigest()
    assert (out / "activity.jsonl").is_file()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_build_views.py -v`
Expected: FAIL (script missing).

- [ ] **Step 3: Implement**

```python
#!/usr/bin/env python3
# scripts/build_views.py
"""Emit the requested transcript views for a pack. CLI wrapper over transcript_views.

Usage: build_views.py <transcript.jsonl> <out_dir> <view> [<view> ...]
`full` is materialized too when requested (a header-stamped copy) — the dispatcher may still
point full-view lenses at the original transcript.jsonl instead; both are valid."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import transcript_views  # noqa: E402


def _read_records(path):
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def main(argv=None):
    ap = argparse.ArgumentParser(description="Emit transcript views")
    ap.add_argument("transcript", type=Path)
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("views", nargs="+")
    ap.add_argument("--tool-result-trunc-len", type=int, default=400)
    args = ap.parse_args(argv)

    bad = [v for v in args.views if v not in transcript_views.VIEWS]
    if bad:
        print("Unknown view(s): {}".format(bad), file=sys.stderr)
        return 2
    sha = hashlib.sha256(Path(args.transcript).read_bytes()).hexdigest()
    records = _read_records(args.transcript)
    paths = transcript_views.emit_views(records, args.views, args.out_dir,
                                        args.tool_result_trunc_len, sha)
    print("Emitted views: {}".format({v: str(p) for v, p in paths.items()}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_build_views.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/build_views.py tests/test_build_views.py
git commit -m "feat(views): build_views.py CLI emits requested views with source hash"
```

---

## Task 7: Convert the `sycophancy` lens to read `conversation`

**Files:**
- Modify: `agents/lenses/sycophancy.md`
- Modify: `agents/lenses/lens-versions.json` (bump + rehash — see note)
- Test: gold-fixture regression via the lens-eval harness (`scripts/eval_lenses.py` / `tests/test_eval_lenses.py` / `tests/lenses/`)

**Interfaces:**
- Consumes: the `TRANSCRIPT` path the dispatcher hands the lens (Task 8).
- Produces: `sycophancy.md` frontmatter declares `inputs.transcript: conversation`; its body reads `TRANSCRIPT` (falls back to `PACK_DIR/transcript.jsonl` if `TRANSCRIPT` is not provided, so the lens still runs under the old dispatch).

- [ ] **Step 1: Add the frontmatter declaration**

Edit the frontmatter block at the top of `agents/lenses/sycophancy.md`:

```yaml
---
name: sycophancy
description: ...(unchanged)...
tools: Read, Bash, Glob, Grep
inputs:
  transcript: conversation
---
```

- [ ] **Step 2: Point the body at the handed-in transcript**

Replace the line (currently `sycophancy.md:43`):

> Read `PACK_DIR/transcript.jsonl` and screen the ASSISTANT's turns for these OBSERVABLE markers:

with:

> Read the transcript at the path you were given as `TRANSCRIPT` (a condensed **conversation view** —
> user + assistant text + thinking, with tool payloads and structural noise already removed; a
> header line describes what was dropped). If no `TRANSCRIPT` was provided, read
> `PACK_DIR/transcript.jsonl`. Screen the ASSISTANT's turns for these OBSERVABLE markers:

(Sycophancy grades only assistant/user text, all of which `conversation` preserves verbatim — no tool_result is needed, so the view is loss-free for this lens.)

- [ ] **Step 3: Refresh the version lock**

The repo pins each lens by sha256 in `agents/lenses/lens-versions.json` (see `test_lens_versions.py`). Bump `sycophancy.version` (patch bump per repo convention — third digit) and regenerate its `sha256`. Use the repo's existing lock-refresh path:

Run: `python -m pytest tests/test_lens_versions.py -v`
Expected: it will FAIL first (hash mismatch), pointing at the exact regeneration command/script the repo uses (e.g. a `lens_versions.py` helper or a documented refresh step). Follow that to update the lock, then re-run to green.

- [ ] **Step 4: Gold-fixture regression (the required Sensor)**

Per the design's migration rule, changing a lens's view is a SCORED change. Run the sycophancy gold fixtures through the lens-eval harness and confirm the verdicts still match:

Run: `python -m pytest tests/test_eval_lenses.py -k sycophancy -v` (and/or the repo's documented `scripts/eval_lenses.py` invocation over `tests/lenses/` sycophancy trials).
Expected: PASS — the `conversation` view yields the same low/medium/high verdicts as `full` on the gold set. If any fixture regresses, STOP: the view dropped signal this lens needed — do not merge.

- [ ] **Step 5: Commit**

```bash
git add agents/lenses/sycophancy.md agents/lenses/lens-versions.json
git commit -m "feat(sycophancy): read the conversation view (tracer for projections)"
```

---

## Task 8: Wire the projector into the generate pipeline

**Files:**
- Modify: `skills/generate/SKILL.md` (Step 4)
- Test: `tests/test-whole-conversation-e2e.sh` (extend) or manual e2e per the repo's e2e pattern

**Interfaces:**
- Consumes: `lens_inputs.requested_views`, `build_views.py`, `transcript_views.VIEWS`.
- Produces: after transcript assembly and before lens dispatch, `PACK_DIR/views/<view>.jsonl` exists for every requested view; each lens is dispatched with an explicit `TRANSCRIPT` path resolved from its declared view (`full` → `PACK_DIR/transcript.jsonl`; else → `PACK_DIR/views/<view>.jsonl`).

- [ ] **Step 1: Add the view-build step to SKILL.md Step 4**

After `mkdir -p "${PACK_DIR}/lenses"` and before the per-lens dispatch loop, insert:

```markdown
**Build the transcript views (cost lever).** Compute the set of views the enabled lenses declare
(each lens's frontmatter `inputs.transcript`, default `full`) and materialize only those, once:

    VIEWS=$("$PYTHON" "${CLAUDE_PLUGIN_ROOT}/scripts/lens_inputs.py" \
        "${CLAUDE_PLUGIN_ROOT}/agents/lenses" "${PACK_DIR}/eval-config.json")
    # VIEWS is a space-separated set excluding "full"; if empty, skip view building.
    "$PYTHON" "${CLAUDE_PLUGIN_ROOT}/scripts/build_views.py" \
        "${PACK_DIR}/transcript.jsonl" "${PACK_DIR}/views" $VIEWS \
        --tool-result-trunc-len "$(jq -r '.toolResultTruncLen // 400' "${PACK_DIR}/eval-config.json")"

For each lens, resolve its TRANSCRIPT path: if the lens declares `full` (or declares nothing),
TRANSCRIPT = `${ABS_PACK_DIR}/transcript.jsonl`; otherwise TRANSCRIPT =
`${ABS_PACK_DIR}/views/<view>.jsonl`.
```

Add a small CLI mode to `scripts/lens_inputs.py` so the skill can call it (extend Task 5's file):

```python
# scripts/lens_inputs.py (add at bottom)
if __name__ == "__main__":
    import json as _json, sys as _sys
    lens_dir, cfg_path = _sys.argv[1], _sys.argv[2]
    cfg = _json.loads(Path(cfg_path).read_text(encoding="utf-8")) if Path(cfg_path).is_file() else {}
    skills = [l.get("skill") for l in (cfg.get("analysisLenses") or []) if l.get("skill")]
    views = requested_views(lens_dir, skills) - {"full"}
    print(" ".join(sorted(views)))
```

- [ ] **Step 2: Extend the dispatch prompt template**

Change the dispatch template (SKILL.md ~350-352) to hand each lens its TRANSCRIPT:

> Run the `<skill>` lens. PACK_DIR is `${ABS_PACK_DIR}`. REPO_ROOT is `${REPO_ROOT}`. DIFF_BASE is
> `${DIFF_BASE}`. TRANSCRIPT is `<resolved per-lens transcript path>`. Read the artifacts (read the
> transcript from TRANSCRIPT), then write your result to `${ABS_PACK_DIR}/lenses/<skill>.json` per
> your schema.

- [ ] **Step 3: Add the CLI unit test for the view-set resolver**

```python
# tests/test_lens_inputs.py (add)
import json, subprocess, sys
from pathlib import Path
SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"

def test_cli_prints_requested_views_excluding_full(tmp_path, monkeypatch):
    lens_dir = tmp_path / "lenses"; lens_dir.mkdir()
    (lens_dir / "syco.md").write_text("---\nname: syco\ninputs:\n  transcript: conversation\n---\nx", encoding="utf-8")
    (lens_dir / "plain.md").write_text("---\nname: plain\n---\nx", encoding="utf-8")
    cfg = tmp_path / "eval-config.json"
    cfg.write_text(json.dumps({"analysisLenses": [{"skill": "syco"}, {"skill": "plain"}]}), encoding="utf-8")
    r = subprocess.run([sys.executable, str(SCRIPTS / "lens_inputs.py"), str(lens_dir), str(cfg)],
                       capture_output=True, text=True)
    assert r.returncode == 0
    assert r.stdout.strip() == "conversation"  # 'full' excluded, 'plain' defaulted to full
```

- [ ] **Step 4: Run the suite + e2e**

Run: `python -m pytest tests/ -q`
Expected: PASS.

Run the whole-conversation e2e and confirm `PACK_DIR/views/conversation.jsonl` is produced and sycophancy still returns a verdict:
Run: `bash tests/test-whole-conversation-e2e.sh`
Expected: PASS; a `views/conversation.jsonl` header shows a non-empty `_dropped` map and the report renders.

- [ ] **Step 5: Commit**

```bash
git add skills/generate/SKILL.md scripts/lens_inputs.py tests/test_lens_inputs.py
git commit -m "feat(generate): build declared views and hand each lens its TRANSCRIPT"
```

---

## Task 9: Cost verification on the 42 MB fixture

**Files:**
- Test: ad-hoc measurement (record the number in the PR description; optional committed check).

**Interfaces:** none.

- [ ] **Step 1: Measure realized reduction**

```bash
BIG=$(find .eval-packs -name transcript.jsonl -size +5M | head -1)
python scripts/build_views.py "$BIG" /tmp/vcheck conversation activity --tool-result-trunc-len 400
ls -la "$BIG" /tmp/vcheck/*.jsonl
```

Expected: `conversation.jsonl` is a small fraction of the 42 MB raw (design target ~4–6 MB whole-view; `conversation` smaller still). Record raw vs each view size.

- [ ] **Step 2: Sanity-check the header**

```bash
head -1 /tmp/vcheck/conversation.jsonl | python -m json.tool
```

Expected: `_dropped` counts dominated by `tool_result` + structural types; `_view`/`_viewVersion`/`_sourceTranscriptSha256` present.

- [ ] **Step 3: Note the number** in the PR body (realized ×-reduction) — this is the feature's whole justification; a silent cap without evidence would be its own Paper Tiger.

---

## Self-Review

- **Spec coverage:** view vocabulary (Tasks 2–3), frontmatter declaration + default-full (Task 5), self-describing header with counts (Task 3), `toolResultTruncLen` new key (Task 4), one-pass N-sink emitter (Task 3/6), lazy materialization of only requested views (Task 8), canonical turnId coordinate (Task 1), sycophancy tracer + scored migration (Task 7), zero-regression default (Tasks 5/8 default-full), cost evidence (Task 9). **Deferred to Plan 2 (by design):** ID-based citation, evaluator→`activity`, truncation-aware verify verdict.
- **Placeholder scan:** none — every code step carries real code; Task 7 Step 3 defers to the repo's existing lock-refresh path rather than inventing one (the failing `test_lens_versions.py` names it).
- **Type consistency:** `project_record(record, view, tool_result_trunc_len)`, `emit_views(records, views, out_dir, tool_result_trunc_len, source_sha256)`, `declared_view(md_text)`, `requested_views(lens_dir, lens_skills)`, `VIEWS`, `VIEW_VERSION` — used consistently across Tasks 2, 3, 5, 6, 8.

## Open items handed to Plan 2

- Trace runtime call sites of `lens_checks.evidence_resolution` (which corpus it resolves quotes against today) and the evaluator's transcript read, then: add `turnId` to finding schemas, resolve quotes by turnId, add the truncation-aware `unverifiable-due-to-truncation` verdict, and move the evaluator to declare `activity`.
