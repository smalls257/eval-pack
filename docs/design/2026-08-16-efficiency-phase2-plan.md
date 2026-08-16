# Efficiency Phase 2 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a cost ledger (instrument eval-pack's own per-lens spend), batch `pull_turn`, and content-hash delta reuse — three deterministic efficiency wins the transcript-view work can't reach.

**Architecture:** All three are deterministic (no model-quality gamble). A) orchestrator writes a one-integer cost sidecar per lens dispatch; a deterministic script aggregates → `pack-cost.json` → a render strip. B) `pull_turn.py` gains `--ids` batch mode. C) a fingerprint keyed by *view-file bytes* (not turnId) decides per-lens reuse; matches reuse the on-disk `lenses/<skill>.json`, mismatches re-run; fail-safe to full re-run.

**Tech Stack:** Python 3 stdlib, pytest. Agent-consumed markdown for the generate/tune SKILL edits. Client JS (`templates/html/scripts.js`) for the render strip.

## Global Constraints

- **Stdlib only.** No new deps. `python3` (not `python`).
- **Deterministic.** No feature depends on model quality; aggregation and reuse decisions are pure functions over on-disk bytes. The LLM's only role in the ledger is copying one integer per lens.
- **Fail-safe, never fake-fresh.** A missing/unreadable prior fingerprint → full re-run (never stale reuse). A missing/malformed cost sidecar → recorded gap (never a silent zero). No Silent Fallback anywhere.
- **Zero regression on a fresh generate.** With no prior pack dir / fingerprint, behavior is byte-identical to today.
- **Sequenced A → B → C.** Ledger first so B/C savings are measurable; C's reuse decisions feed the ledger's `reused` flag.
- **Reuse existing plumbing:** persisted pack dir (`render_html.py:804`), per-lens `lenses/<skill>.json` files, config-gated assembly orphan guard (`assemble_lenses.py:66-72`), the `subagent_tokens` regex (`extract_metrics.py:11`), `lens_versions.load_lock` (`lens_versions.py:26-31`).

---

## File Structure

- `scripts/pack_cost.py` — **create.** Aggregate per-lens cost sidecars (or parsed session transcript, per Task 1) → `pack-cost.json`. Pure functions + CLI.
- `scripts/pull_turn.py` — **modify.** Add `--ids` batch mode; keep single-id.
- `scripts/pack_fingerprint.py` — **create.** Compute per-lens + whole-pack reuse keys; write/read `pack-fingerprint.json`; decide reuse.
- `skills/generate/SKILL.md` — **modify.** Step 4/4.5: fingerprint reuse gate before dispatch; write cost sidecars; run `pack_cost.py`.
- `skills/tune/SKILL.md` — **modify.** Same reuse gate + cost aggregation on the re-run path.
- `scripts/render_html.py` — **modify.** Thread `pack-cost.json` into the template data (mirror `metrics.json` at `:723`).
- `templates/html/scripts.js` — **modify.** "Cost of this pack" stats group (mirror the `Subagent tokens` group at `:238-241`).
- `agents/lenses/*.md` (skeleton lenses) — **modify.** Batch-your-pulls nudge + version re-lock.
- `tests/test_pack_cost.py`, `tests/test_pull_turn.py`, `tests/test_pack_fingerprint.py` — **create/modify.**

---

## Task 1: Ledger capture — spike + `pack_cost.py` aggregation

**Files:**
- Create: `scripts/pack_cost.py`
- Test: `tests/test_pack_cost.py`

**Interfaces:**
- Produces: `aggregate(pack_dir) -> dict` reading `${pack_dir}/lenses/*.cost.json` sidecars → `{"perLens": [{skill, tokens, model, reused}], "evaluatorTokens": int, "totalTokens": int}`. A malformed/missing sidecar for a configured lens → an entry with `"tokens": null, "gap": "<reason>"` (recorded gap, never silent 0). CLI writes `${pack_dir}/pack-cost.json`.

- [ ] **Step 1: Spike (investigate, then decide) — record the finding in the report**

Before writing the aggregator's *input* path, determine whether a deterministic script can parse the **generate session's own transcript** for the lens Agent tool_results (reusing `extract_metrics.extract_subagent_tokens`), which would let us skip the orchestrator-written sidecars entirely.

Investigate: at generate-time, is the *current* Claude Code session's transcript path knowable to a script (env var, a stable "most-recently-modified jsonl" in the CC project dir, or a path the skill already holds)? Note that `TRANSCRIPT_PATH` in the skill is the **evaluated** session, not the generate session.

Decision rule: if a clean, non-fragile handle to the generate session transcript exists → add a `--from-session-transcript <path>` mode to `pack_cost.py` and have the SKILL use it (no sidecars). If not → the **sidecar path is the baseline** (Steps 3-5 below). Record which path you took and why in the task report. The sidecar path is always implemented as the guaranteed fallback regardless.

- [ ] **Step 2: Write the failing tests (sidecar aggregation — the guaranteed path)**

```python
# tests/test_pack_cost.py
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import pack_cost

def _sidecar(d, skill, tokens, model="sonnet", reused=False):
    (d / "lenses").mkdir(parents=True, exist_ok=True)
    (d / "lenses" / f"{skill}.cost.json").write_text(
        json.dumps({"skill": skill, "tokens": tokens, "model": model, "reused": reused}), encoding="utf-8")

def test_aggregate_sums_and_lists(tmp_path):
    _sidecar(tmp_path, "sycophancy", 44155)
    _sidecar(tmp_path, "review", 88519, model="opus")
    _sidecar(tmp_path, "eval-pack-evaluator", 51000, model="opus")
    out = pack_cost.aggregate(tmp_path)
    lenses = {e["skill"]: e for e in out["perLens"]}
    assert lenses["sycophancy"]["tokens"] == 44155
    assert out["evaluatorTokens"] == 51000        # evaluator pulled out of perLens
    assert out["totalTokens"] == 44155 + 88519 + 51000

def test_reused_lens_zero_tokens(tmp_path):
    _sidecar(tmp_path, "sycophancy", 0, reused=True)
    out = pack_cost.aggregate(tmp_path)
    e = out["perLens"][0]
    assert e["reused"] is True and e["tokens"] == 0

def test_malformed_sidecar_is_a_recorded_gap_not_zero(tmp_path):
    (tmp_path / "lenses").mkdir()
    (tmp_path / "lenses" / "friction.cost.json").write_text("{not json", encoding="utf-8")
    out = pack_cost.aggregate(tmp_path)
    e = next(x for x in out["perLens"] if x["skill"] == "friction")
    assert e["tokens"] is None and "gap" in e   # recorded gap, never silent 0
```

- [ ] **Step 3: Run to verify it fails**

Run: `python3 -m pytest tests/test_pack_cost.py -v`  → FAIL (`ModuleNotFoundError`).

- [ ] **Step 4: Implement**

```python
#!/usr/bin/env python3
# scripts/pack_cost.py
"""Aggregate eval-pack's OWN per-lens token spend into pack-cost.json.

The per-lens count lives only in the parent orchestrator's Agent tool result
(a lens subagent cannot see its own usage), so generate/tune write a one-integer
sidecar `lenses/<skill>.cost.json` per dispatch. This script aggregates them
deterministically — it never trusts the LLM to do math, only to copy one int.
A missing/malformed sidecar for a configured lens is a RECORDED GAP, not a 0."""
import argparse
import json
import sys
from pathlib import Path

_EVALUATOR = "eval-pack-evaluator"


def _read_sidecar(path):
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"skill": path.stem[:-5] if path.stem.endswith(".cost") else path.stem,
                "tokens": None, "gap": "unreadable sidecar ({})".format(exc)}
    tokens = d.get("tokens")
    if not isinstance(tokens, int) or isinstance(tokens, bool):
        return {"skill": d.get("skill", path.stem), "tokens": None,
                "gap": "non-integer tokens"}
    return {"skill": d.get("skill", path.stem), "tokens": tokens,
            "model": d.get("model"), "reused": bool(d.get("reused", False))}


def aggregate(pack_dir):
    pack = Path(pack_dir)
    lens_dir = pack / "lenses"
    entries = []
    if lens_dir.is_dir():
        for f in sorted(lens_dir.glob("*.cost.json")):
            entries.append(_read_sidecar(f))
    per_lens = [e for e in entries if e["skill"] != _EVALUATOR]
    evaluator = next((e["tokens"] for e in entries
                      if e["skill"] == _EVALUATOR and isinstance(e["tokens"], int)), 0)
    total = sum(e["tokens"] for e in entries if isinstance(e["tokens"], int))
    return {"perLens": per_lens, "evaluatorTokens": evaluator, "totalTokens": total}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Aggregate per-lens eval-pack cost")
    ap.add_argument("pack_dir")
    args = ap.parse_args(argv)
    out = aggregate(args.pack_dir)
    (Path(args.pack_dir) / "pack-cost.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    gaps = [e["skill"] for e in out["perLens"] if e["tokens"] is None]
    print("pack-cost.json: {} lenses, total {} tokens{}".format(
        len(out["perLens"]), out["totalTokens"],
        "" if not gaps else " (gaps: {})".format(", ".join(gaps))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

(If Task 1 Step 1 chose the transcript-parse path, add a `from_session_transcript(path)` function that reuses `extract_metrics.extract_subagent_tokens` and returns the same shape; wire it behind a `--from-session-transcript` flag. The sidecar `aggregate` stays as the fallback.)

- [ ] **Step 5: Run + full suite**

Run: `python3 -m pytest tests/test_pack_cost.py -v` → PASS. Then `python3 -m pytest tests/ -q`.

- [ ] **Step 6: Commit**

```bash
git add scripts/pack_cost.py tests/test_pack_cost.py
git commit -m "feat(cost): pack_cost.py — deterministic per-lens spend aggregation"
```

---

## Task 2: Capture cost sidecars + run aggregation in `generate`

**Files:**
- Modify: `skills/generate/SKILL.md` (Step 4 lens dispatch ~`:330-383`, Step 4.5 evaluator dispatch ~`:433-450`)
- Test: full suite + manual reading (agent-consumed markdown)

**Interfaces:**
- Consumes: `pack_cost.py` (Task 1).
- Produces: after each lens/evaluator dispatch, a `lenses/<skill>.cost.json` sidecar exists with the dispatch's `subagent_tokens` + model; after Step 4.5, `pack_cost.py` has written `pack-cost.json`.

- [ ] **Step 1: Add the sidecar-capture instruction to the lens dispatch**

In Step 4, after the "Each lens WRITES its result to `lenses/<skill>.json`" text, add: "After each lens subagent returns, record its cost: write `${ABS_PACK_DIR}/lenses/<skill>.cost.json` = `{\"skill\": \"<skill>\", \"tokens\": <the subagent_tokens from the Agent result>, \"model\": \"<the model used>\", \"reused\": false}`. This is a mechanical copy of the integer the Agent result reported — do not compute it."

- [ ] **Step 2: Same for the evaluator (Step 4.5)**

After the evaluator dispatch, add the same sidecar write with `skill: "eval-pack-evaluator"`.

- [ ] **Step 3: Run the aggregator after Step 4.5**

Add, after the evaluator + `validate_contracts.py`: `"$PYTHON" "${CLAUDE_PLUGIN_ROOT}/scripts/pack_cost.py" "${PACK_DIR}"`.

- [ ] **Step 4: Verify**

Run: `python3 -m pytest tests/ -q` (green — markdown change). Read the diff; confirm the sidecar write is scoped to each dispatch and the aggregator runs once.

- [ ] **Step 5: Commit**

```bash
git add skills/generate/SKILL.md
git commit -m "feat(generate): capture per-lens cost sidecars + aggregate pack-cost.json"
```

---

## Task 3: Render the "Cost of this pack" strip

**Files:**
- Modify: `scripts/render_html.py` (`:723` data dict), `templates/html/scripts.js` (`renderStats` `:217-254`)
- Test: `tests/test_report_config.py` / render tests + manual

**Interfaces:**
- Consumes: `pack-cost.json`.
- Produces: the report's stats region shows a per-lens spend group + total.

- [ ] **Step 1: Thread `pack-cost.json` into the template data**

In `render_html.py` near `:723` (`"metrics": read_json(pack_dir / "metrics.json")`), add `"packCost": read_json(pack_dir / "pack-cost.json")` to the `data` dict. Absent file → `read_json` returns its empty default (confirm the helper's behavior; a missing ledger must not crash render).

- [ ] **Step 2: Add the render group**

In `scripts.js` `renderStats` (`:217-254`), mirror the `Subagent tokens` group (`:238-241`): a "Cost of this pack" group listing `packCost.perLens` (skill → tokens, "reused" badge when `reused`), plus `evaluatorTokens` and `totalTokens`. Guard on `packCost` being present (old packs won't have it).

- [ ] **Step 3: Test**

Run the render tests (`python3 -m pytest tests/test_report_config.py tests/test_render_config_threading.py -q`), then full suite. If a JS test harness exists (`tests/*.test.mjs`), add a case that `renderStats` emits the cost group when `packCost` is present and omits it when absent.

- [ ] **Step 4: Commit**

```bash
git add scripts/render_html.py templates/html/scripts.js
git commit -m "feat(report): render the cost-of-this-pack strip"
```

---

## Task 4: `pull_turn.py --ids` batch mode

**Files:**
- Modify: `scripts/pull_turn.py`
- Test: `tests/test_pull_turn.py`

**Interfaces:**
- Produces: `pull_batch(transcript, turn_ids, field=None) -> dict[int, str]` — one file scan, returns `{turnId: body}` for each requested id present; ids absent from the transcript are reported (not silently dropped). CLI: `pull_turn.py <transcript> --ids 12,47,301 [--field ...]` prints labeled, splittable output. Single positional `turn_id` unchanged.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_pull_turn.py (add)
def test_pull_batch_one_scan_returns_each(tmp_path):
    p = _t(tmp_path)   # existing fixture with turnId 5 (assistant) + 6 (tool_result)
    got = pull_turn.pull_batch(p, [5, 6], field="text")
    assert "done" in got[5]                 # turn 5 text
    assert 6 in got                         # turn 6 present (empty text ok)

def test_pull_batch_reports_missing(tmp_path):
    p = _t(tmp_path)
    got = pull_turn.pull_batch(p, [6, 99], field="tool_result")
    assert 6 in got and 99 not in got       # 99 absent, not fabricated

def test_cli_ids_labeled_output(tmp_path):
    p = _t(tmp_path)
    r = subprocess.run([sys.executable, str(SCRIPTS/"pull_turn.py"), str(p),
                        "--ids", "5,6", "--field", "text"], capture_output=True, text=True)
    assert r.returncode == 0
    assert '"5"' in r.stdout and '"6"' in r.stdout   # JSON-object output keyed by id
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_pull_turn.py -k batch -v` → FAIL.

- [ ] **Step 3: Implement**

Add to `pull_turn.py`: a `pull_batch` that scans the file once, building `{turnId: record}` for the requested set (a `set` for O(1) membership), then applies the existing per-field extraction to each. Make `--ids` and the positional `turn_id` mutually exclusive in argparse. CLI batch output = `json.dumps({str(tid): body, ...})` (unambiguous, splittable). Missing ids: omit from the dict and print a stderr note listing them (nonzero exit only if *every* requested id is missing — a partial hit is success).

```python
def pull_batch(transcript_path, turn_ids, field=None):
    wanted = set(turn_ids)
    found = {}
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
            tid = o.get("turnId")
            if tid in wanted:
                found[tid] = _extract_field(o, field)   # refactor field logic out of pull()
                if len(found) == len(wanted):
                    break
    return found
```

(Refactor the field-extraction body of `pull()` into a shared `_extract_field(record, field)` so single and batch share it.)

- [ ] **Step 4: Run + full suite**

Run: `python3 -m pytest tests/test_pull_turn.py -v` (incl. the existing single-id cases — back-compat) then `python3 -m pytest tests/ -q`.

- [ ] **Step 5: Commit**

```bash
git add scripts/pull_turn.py tests/test_pull_turn.py
git commit -m "feat(views): pull_turn --ids batch mode (one scan, N turns)"
```

---

## Task 5: Batch-your-pulls prompt nudge

**Files:**
- Modify: the skeleton-view lenses (`agents/lenses/{verification-rigor,sycophancy,business-risk,requirement-drift}.md`), `agents/lenses/lens-versions.json`
- Test: `test_lens_versions.py`, `test_graded_lens_contracts.py`, gold reruns, full suite

**Interfaces:**
- Produces: each skeleton lens's pull instruction tells it to batch. Contracts/schemas unchanged.

- [ ] **Step 1: Add the nudge**

In each skeleton lens's pull-on-demand instruction, append: "If you need several turns' full bodies, collect their turnIds and pull them in **one** call: `pull_turn.py \"$RAW_TRANSCRIPT\" --ids 12,47,301 --field tool_result` — not one at a time." Do not change the output contract JSON or schema.

- [ ] **Step 2: Re-lock versions**

Bump each edited lens's patch digit in `lens-versions.json` + refresh sha256 (`python3 -c "...lens_versions.hash_file(...)"`). Update `test_assemble_lenses.py` if any edited lens's version is pinned there.

- [ ] **Step 3: Verify**

Run: `python3 -m pytest tests/test_lens_versions.py tests/test_graded_lens_contracts.py -v`; gold reruns for the guarded lenses (requirement-drift, and sycophancy real bundle); full suite.

- [ ] **Step 4: Commit**

```bash
git add agents/lenses/*.md agents/lenses/lens-versions.json tests/test_assemble_lenses.py
git commit -m "feat(lenses): nudge skeleton lenses to batch pulls via --ids"
```

---

## Task 6: `pack_fingerprint.py` — reuse keys

**Files:**
- Create: `scripts/pack_fingerprint.py`
- Test: `tests/test_pack_fingerprint.py`

**Interfaces:**
- Produces:
  - `lens_key(view_bytes, lens_version, model, diff_base) -> str` (sha256 hex).
  - `compute(pack_dir, config, diff_base) -> dict` → `{"perLens": {skill: key}, "whole": key}` (per-lens keys over each lens's resolved view file bytes + its locked version + model; whole = digest of the ordered per-lens keys + resolved-config hash).
  - `decide_reuse(prior, current) -> {"reuseAll": bool, "reuse": set[skill], "rerun": set[skill]}` — a lens is reusable iff its key matches prior AND (checked by caller) `lenses/<skill>.json` exists. Missing/unreadable prior → reuse nothing (fail-safe).
  - CLI writes `${pack_dir}/pack-fingerprint.json`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_pack_fingerprint.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import pack_fingerprint as pf

def test_lens_key_flips_on_each_axis():
    base = pf.lens_key(b"view-bytes", "1.0.0", "sonnet", "HEAD~1")
    assert pf.lens_key(b"view-bytes-CHANGED", "1.0.0", "sonnet", "HEAD~1") != base
    assert pf.lens_key(b"view-bytes", "1.0.1", "sonnet", "HEAD~1") != base
    assert pf.lens_key(b"view-bytes", "1.0.0", "opus", "HEAD~1") != base
    assert pf.lens_key(b"view-bytes", "1.0.0", "sonnet", "HEAD~2") != base
    assert pf.lens_key(b"view-bytes", "1.0.0", "sonnet", "HEAD~1") == base  # stable

def test_decide_reuse_matches_and_mismatches():
    prior = {"perLens": {"a": "K1", "b": "K2"}, "whole": "W"}
    cur   = {"perLens": {"a": "K1", "b": "K2-changed"}, "whole": "W2"}
    d = pf.decide_reuse(prior, cur)
    assert d["reuse"] == {"a"} and d["rerun"] == {"b"} and d["reuseAll"] is False

def test_missing_prior_reuses_nothing():
    cur = {"perLens": {"a": "K1"}, "whole": "W"}
    d = pf.decide_reuse(None, cur)      # fail-safe
    assert d["reuse"] == set() and d["rerun"] == {"a"} and d["reuseAll"] is False

def test_whole_match_reuses_all():
    prior = {"perLens": {"a": "K1"}, "whole": "W"}
    cur   = {"perLens": {"a": "K1"}, "whole": "W"}
    assert pf.decide_reuse(prior, cur)["reuseAll"] is True
```

- [ ] **Step 2: Run to verify it fails** → `python3 -m pytest tests/test_pack_fingerprint.py -v` FAIL.

- [ ] **Step 3: Implement**

```python
#!/usr/bin/env python3
# scripts/pack_fingerprint.py
"""Content-hash reuse keys for delta re-runs. Keyed by the lens's ACTUAL input
bytes (its resolved view file) — never by turnId, which is a post-sort ordinal
that shifts under membership changes. A lens is reusable iff every input axis is
byte-identical to the prior round. Missing prior => reuse nothing (fail-safe)."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lens_versions  # noqa: E402


def lens_key(view_bytes, lens_version, model, diff_base):
    h = hashlib.sha256()
    for part in (view_bytes, str(lens_version).encode(), str(model).encode(), str(diff_base).encode()):
        h.update(hashlib.sha256(part).digest())   # length-framed
    return h.hexdigest()


def _view_bytes(pack_dir, view):
    p = Path(pack_dir) / ("transcript.jsonl" if view in (None, "full")
                          else "views/{}.jsonl".format(view))
    return p.read_bytes() if p.is_file() else b""


def compute(pack_dir, lenses, diff_base):
    """`lenses` = resolved analysisLenses [{skill, model?, ...}] with a resolved `view`."""
    lock = lens_versions.load_lock()
    per = {}
    for l in lenses:
        skill = l.get("skill")
        ver = (lock.get(skill) or {}).get("version", "?")
        per[skill] = lens_key(_view_bytes(pack_dir, l.get("view")), ver, l.get("model"), diff_base)
    whole = hashlib.sha256(json.dumps(per, sort_keys=True).encode()).hexdigest()
    return {"perLens": per, "whole": whole}


def decide_reuse(prior, current):
    if not prior or not isinstance(prior, dict):
        return {"reuseAll": False, "reuse": set(), "rerun": set(current["perLens"])}
    if prior.get("whole") == current.get("whole"):
        return {"reuseAll": True, "reuse": set(current["perLens"]), "rerun": set()}
    prior_p = prior.get("perLens") or {}
    reuse = {s for s, k in current["perLens"].items() if prior_p.get(s) == k}
    rerun = set(current["perLens"]) - reuse
    return {"reuseAll": False, "reuse": reuse, "rerun": rerun}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("pack_dir")
    ap.add_argument("--config", required=True, help="resolved eval-config.json")
    ap.add_argument("--diff-base", default="")
    args = ap.parse_args(argv)
    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    lenses = cfg.get("analysisLenses") or []
    # resolve each lens's declared view (reuse lens_inputs.declared_view over its .md)
    import lens_inputs
    lens_dir = Path(__file__).resolve().parent.parent / "agents" / "lenses"
    for l in lenses:
        md = lens_dir / (l.get("skill", "") + ".md")
        l["view"] = lens_inputs.declared_view(md.read_text(encoding="utf-8")) if md.is_file() else "full"
    out = compute(args.pack_dir, lenses, args.diff_base)
    (Path(args.pack_dir) / "pack-fingerprint.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("pack-fingerprint.json: {} lenses".format(len(out["perLens"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run + full suite** → `python3 -m pytest tests/test_pack_fingerprint.py -v` PASS, then `tests/ -q`.

- [ ] **Step 5: Commit**

```bash
git add scripts/pack_fingerprint.py tests/test_pack_fingerprint.py
git commit -m "feat(delta): pack_fingerprint.py — content-hash reuse keys (not turnId)"
```

---

## Task 7: Wire delta reuse into `generate` + `tune`

**Files:**
- Modify: `skills/generate/SKILL.md` (Step 4), `skills/tune/SKILL.md` (batch re-run path)
- Test: full suite + manual reading

**Interfaces:**
- Consumes: `pack_fingerprint.py`, the persisted prior `pack-fingerprint.json`, the persisted `lenses/<skill>.json`.
- Produces: on a re-run, matched lenses are skipped (their on-disk result kept + stamped `reused: true` in the cost sidecar with `tokens: 0`); mismatched lenses are re-dispatched; whole-match skips everything before render.

- [ ] **Step 1: generate Step 4 — compute + compare fingerprint before dispatch**

After building views and BEFORE the lens dispatch loop, add: compute the current fingerprint (`pack_fingerprint.py <PACK_DIR> --config eval-config.json --diff-base $DIFF_BASE` writes `pack-fingerprint.json`); if a prior `pack-fingerprint.json` was restored into the pack dir, run the reuse decision. For each lens: **if reusable AND `lenses/<skill>.json` exists → skip dispatch; write its cost sidecar `{tokens: 0, reused: true}`; keep the on-disk result.** Else dispatch as normal (and write its real cost sidecar). Note the whole-match C1 fast path: if `reuseAll`, skip all lens dispatches and the evaluator, keep on-disk `analysis.json`, go to render.

Provide the exact decision as a small helper invocation the skill runs (e.g. `pack_fingerprint.py --decide <prior> <current>` printing the reuse/rerun sets) so the orchestrator doesn't hand-diff hashes — add a `--decide` subcommand to `pack_fingerprint.py` that prints the `decide_reuse` result as JSON. (Add this to Task 6 if cleaner; the plan allows either — implement the `--decide` CLI where the wiring needs it.)

- [ ] **Step 2: tune — same gate on the batch re-run path**

In `tune/SKILL.md`'s "dispatch every lens" section (`:81-87`), insert the same fingerprint gate so re-eval reuses unchanged lenses. The single-lens mode (`:116-165`) already reuses the rest — leave it, but it may now also skip the named lens if its inputs are unchanged (note this as a minor behavior refinement).

- [ ] **Step 3: Fail-safe wording**

State explicitly in both skills: "If no prior `pack-fingerprint.json` exists, or it is unreadable, dispatch ALL lenses — never reuse on uncertainty." (Fresh generate = full run, byte-identical to today.)

- [ ] **Step 4: Verify**

Run: `python3 -m pytest tests/ -q` (green — markdown). Read the diffs. Manually reason through: (a) fresh generate, no prior → all dispatch; (b) identical re-run → whole-match, skip all; (c) one lens `.md` edited → only that lens re-runs; (d) transcript changed → affected lenses re-run.

- [ ] **Step 5: Commit**

```bash
git add skills/generate/SKILL.md skills/tune/SKILL.md scripts/pack_fingerprint.py
git commit -m "feat(delta): reuse unchanged lenses across generate/tune (C1+C2), fail-safe"
```

---

## Task 8: End-to-end verification + realized-savings note

**Files:** none (verification only).

- [ ] **Step 1: Fresh-generate regression**

Confirm a fresh generate on a session with no prior pack dir produces the same lens outputs as before + a populated `pack-cost.json` (all lenses `reused: false`). No behavior change beyond the new artifact.

- [ ] **Step 2: Delta savings measurement**

Regenerate the same pack twice (identical inputs). Second run: `pack-fingerprint.json` whole-match → all lenses skipped → `pack-cost.json` shows every lens `reused: true, tokens: 0`. Record the realized second-run token cost (~evaluator + deterministic scripts only) vs first-run in the PR body.

- [ ] **Step 3: Partial-delta check**

Edit one lens `.md` (bump its version), regenerate: confirm only that lens re-dispatches (cost sidecar has real tokens), the rest show `reused: true`.

- [ ] **Step 4: Full suite** → `python3 -m pytest tests/ -q`.

---

## Self-Review

- **Spec coverage:** ledger capture + deterministic aggregation (Tasks 1-2), render strip (Task 3), spike (Task 1 Step 1), batch pulls + nudge (Tasks 4-5), fingerprint keyed by view bytes not turnId (Task 6), reuse wiring C1+C2 + fail-safe (Task 7), reused-feeds-ledger (Task 7 Step 1 writes `reused` sidecars → Task 1 aggregation surfaces them). Deferred items (C3, pre-split, cheap-first/candidate/narrator, batch-API) are out of scope per spec.
- **Placeholder scan:** none — real code in every code step; the `--decide` CLI is called out as an explicit sub-item, not a vague "add a flag."
- **Type consistency:** `aggregate(pack_dir)`, `pull_batch(transcript, turn_ids, field)` + `_extract_field(record, field)`, `lens_key(view_bytes, lens_version, model, diff_base)` / `compute(pack_dir, lenses, diff_base)` / `decide_reuse(prior, current)` — used consistently across Tasks 1, 4, 6, 7. Sidecar shape `{skill, tokens, model, reused}` is written in Task 2, read in Task 1, stamped `reused` in Task 7.

## Out of scope (deferred)

- Turn-level delta (C3), view pre-splitting, cheap-first escalation, candidate mining, output narrator, Batch API / shared-prefix caching — per the spec's deferral list.
