# Lens Evaluator — Part 4: Developer-Ownership bundle (grounded) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Evaluate the `user-improvements` (Developer Ownership) lens end-to-end with a grounded 3-fixture bundle, generalizing the engine so a lens can keep its domain-natural output shape (`items[{kind}]`) and still get evidence-grounded.

**Architecture:** A small engine **adapter** — the output contract may declare `findingsKey` (default `"findings"`) and `typeField` (default `"type"`); evidence-resolution, the contract validator, rule-consistency, and output-assertion read those instead of hardcoding `findings`/`type`. This is backward-compatible (drift/syco declare neither → defaults). Then `user-improvements.md` declares `findingsKey:"items"`, `typeField:"kind"`, adds `quote`/`evidential` to each item, and the bundle ships 1 HIGH + 2 LOW fixtures with recorded trials. Vetting (the developer demanding verification / challenging claims / not taking output at face value) is an explicit basis claim.

**Tech Stack:** Python 3 stdlib only. Tests are `unittest.TestCase`, run via `python3 -m pytest`.

## Global Constraints

- **Runtime scripts: Python 3 stdlib only.** No third-party imports under `scripts/`.
- **Repo import convention:** `scripts/` not a package; bare-name sibling imports; tests use the `sys.path.insert(...scripts)` bootstrap + bare import; `unittest.TestCase`.
- **`python` is not on PATH — use `python3`.**
- **Backward compatibility is mandatory:** the adapter defaults (`findingsKey="findings"`, `typeField="type"`) must leave drift/sycophancy behavior byte-identical — their contracts declare neither key. The full suite (currently 374) must stay green.
- **Editing `agents/lenses/user-improvements.md` changes its sha** → re-lock `lens-versions.json`.
- **The gate stays deterministic + offline:** the e2e replays committed trials; no live dispatch, no network.
- **Fixtures self-contained, permissive sources:** daaain sessions are MIT; WildChat is ODC-BY (attribute). Transcript-only (no repo/diff) — ownership is judged from the transcript.

## The adapter (data shapes)

Output contract gains two optional keys:
```json
{ "gradedField": "level", "levelOrdinal": ["low","medium","high"],
  "findingsKey": "items", "typeField": "kind", "findingTypes": ["strength","improvement"] }
```
- `findingsKey` — the array on the lens output that carries evidence-bearing entries. Default `"findings"`.
- `typeField` — the per-entry field naming the entry's type. Default `"type"`.
- Every place the engine currently reads `output.get("findings")` reads `output.get(findingsKey)`; every `f.get("type")` reads `f.get(typeField)`.

`user-improvements` item (post-change): `{"kind": "strength"|"improvement", "title": "...", "quote": "verbatim transcript span", "evidential": true, "detail": "..."}`.

---

### Task 1: Contract-validator adapter (`lens_contract.py`)

**Files:**
- Modify: `scripts/lens_contract.py`
- Test: `tests/test_lens_contract.py` (add cases)

**Interfaces:**
- `validate_output(output, contract)` reads `contract.get("findingsKey","findings")` and `contract.get("typeField","type")` for the finding loop. Signature unchanged. Default behavior identical for contracts without those keys.

- [ ] **Step 1: Write the failing test** — add to `class TestLensContract` in `tests/test_lens_contract.py`:

```python
    def test_adapter_items_kind_contract(self):
        c = {"gradedField": "level", "levelOrdinal": ["low", "medium", "high"],
             "findingsKey": "items", "typeField": "kind", "findingTypes": ["strength", "improvement"]}
        ok = {"level": "high", "items": [{"kind": "strength", "quote": "q", "detail": "d"}]}
        self.assertEqual(lens_contract.validate_output(ok, c), [])
        bad_type = {"level": "high", "items": [{"kind": "bogus", "quote": "q"}]}
        self.assertTrue(lens_contract.validate_output(bad_type, c))
        no_quote = {"level": "high", "items": [{"kind": "strength"}]}  # evidential default -> needs quote
        self.assertTrue(lens_contract.validate_output(no_quote, c))

    def test_defaults_unchanged_for_findings_type(self):
        c = {"gradedField": "score", "findingTypes": ["met"]}
        out = {"score": 80, "findings": [{"type": "met", "quote": "q"}]}
        self.assertEqual(lens_contract.validate_output(out, c), [])
```

- [ ] **Step 2: Run test to verify it fails** — `python3 -m pytest tests/test_lens_contract.py -v` → the adapter test fails (items/kind not read yet).

- [ ] **Step 3: Write minimal implementation** — in `scripts/lens_contract.py`, replace the finding-loop section so it reads the adapter keys:

```python
    if "findingTypes" in contract:
        allowed = set(contract.get("findingTypes") or [])
        fkey = contract.get("findingsKey", "findings")
        tfield = contract.get("typeField", "type")
        for i, f in enumerate(output.get(fkey) or []):
            if f.get(tfield) not in allowed:
                v.append("{}[{}] {} {!r} not in {}".format(fkey, i, tfield, f.get(tfield), sorted(allowed)))
            if f.get("evidential", True) and not (f.get("quote") or "").strip():
                v.append("{}[{}] is evidential but has no quote".format(fkey, i))
    return v
```

- [ ] **Step 4: Run test to verify it passes** — `python3 -m pytest tests/test_lens_contract.py -v` → PASS (existing + 2 new).

- [ ] **Step 5: Commit** — `git add scripts/lens_contract.py tests/test_lens_contract.py && git commit -m "feat(lens-eval): contract validator reads findingsKey/typeField adapter"`

---

### Task 2: Checks adapter (`lens_checks.py`)

**Files:**
- Modify: `scripts/lens_checks.py`
- Test: `tests/test_lens_checks_adapter.py`

**Interfaces:**
- `evidence_resolution(output, corpus, findings_key="findings")` — new optional 3rd arg naming the evidence-bearing collection; default `"findings"` (existing callers unaffected).
- `assert_one(output, gold, ordinal, findings_key="findings")` — the `findings` include/exclude block reads `output.get(findings_key)`; `output_assertion(trials, gold, ordinal, findings_key="findings")` threads it through.
- `rule_consistency(output, rules, ordinal, findings_key="findings")` — filters evidential entries and evaluates rules over `output.get(findings_key)`. (Note: `lens_rules._finding_types` reads `output.get("findings")`; to keep the closed grammar untouched, `rule_consistency` normalizes by passing a dict whose `"findings"` key is the evidential-filtered `findings_key` collection with each entry's type under `"type"`.)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_lens_checks_adapter.py
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import lens_checks  # noqa: E402

CORPUS = "user: Are you sure the HTML is the issue?\nassistant: you are right"
ORD = ["low", "medium", "high"]

class TestChecksAdapter(unittest.TestCase):
    def test_evidence_resolution_over_items(self):
        out = {"items": [{"kind": "strength", "quote": "Are you sure the HTML is the issue", "evidential": True}]}
        self.assertEqual(lens_checks.evidence_resolution(out, CORPUS, findings_key="items"), (True, []))
        bad = {"items": [{"kind": "strength", "quote": "never said this", "evidential": True}]}
        self.assertFalse(lens_checks.evidence_resolution(bad, CORPUS, findings_key="items")[0])

    def test_assert_one_findings_over_items(self):
        out = {"level": "high", "items": [{"kind": "strength"}]}
        gold = {"level": {"min": "medium"}, "findings": {"include": ["strength"]}}
        self.assertTrue(lens_checks.assert_one(out, gold, ORD, findings_key="items"))

    def test_defaults_unchanged(self):
        out = {"findings": [{"type": "capitulation", "quote": "x", "evidential": True}]}
        self.assertEqual(lens_checks.evidence_resolution(out, "x"), (True, []))
        self.assertTrue(lens_checks.assert_one({"score": 90}, {"score": {"min": 70, "max": 100}}, ORD))

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails** — `python3 -m pytest tests/test_lens_checks_adapter.py -v` → FAIL (findings_key kwarg not accepted).

- [ ] **Step 3: Write minimal implementation** — in `scripts/lens_checks.py`:

`evidence_resolution` signature + loop:
```python
def evidence_resolution(output, corpus, findings_key="findings"):
    hay = _norm(corpus)
    msgs = []
    for i, f in enumerate(output.get(findings_key) or []):
        if not f.get("evidential", True):
            continue
        q = _norm(f.get("quote"))
        if not q or q not in hay:
            msgs.append("{}[{}] quote unresolved: {!r}".format(findings_key, i, f.get("quote")))
    return (not msgs, msgs)
```

`rule_consistency` — normalize the evidence collection into a `findings`/`type` shape for the closed-grammar evaluator:
```python
def rule_consistency(output, rules, ordinal, findings_key="findings", type_field="type"):
    entries = [f for f in (output.get(findings_key) or []) if f.get("evidential", True)]
    normalized = {**output, "findings": [{"type": e.get(type_field)} for e in entries],
                  "level": output.get("level"), "score": output.get("score")}
    msgs = check_rules(rules, normalized, ordinal)
    return (not msgs, msgs)
```

`assert_one` + `output_assertion` — thread `findings_key`:
```python
def assert_one(output, gold, ordinal, findings_key="findings"):
    ...  # score + level branches unchanged
    if "findings" in gold:
        types = {f.get("type", f.get("kind")) for f in (output.get(findings_key) or [])}
        ...  # include/exclude unchanged, using this `types`

def output_assertion(trials, gold, ordinal, findings_key="findings"):
    n = len(trials)
    meeting = sum(1 for t in trials if assert_one(t, gold, ordinal, findings_key))
    return {"passed": n > 0 and meeting * 3 >= n * 2, "meeting": meeting, "n": n}
```
(`assert_one`'s findings block reads `f.get("type", f.get("kind"))` so it works for either shape without a second kwarg for the type field.)

- [ ] **Step 4: Run test to verify it passes** — `python3 -m pytest tests/test_lens_checks_adapter.py tests/test_lens_checks_evidence.py tests/test_lens_checks_rules.py tests/test_lens_checks_assertion.py -v` → PASS (new + existing).

- [ ] **Step 5: Commit** — `git add scripts/lens_checks.py tests/test_lens_checks_adapter.py && git commit -m "feat(lens-eval): checks read findings_key adapter (default findings)"`

---

### Task 3: Orchestrator threads the adapter (`eval_lenses.py`)

**Files:**
- Modify: `scripts/eval_lenses.py`
- Test: `tests/test_eval_lenses.py` (add one case)

**Interfaces:**
- `evaluate_bundle` reads `contract.get("findingsKey","findings")` and passes it to `evidence_resolution`, `rule_consistency`, and `output_assertion`.

- [ ] **Step 1: Write the failing test** — add to `tests/test_eval_lenses.py`:

```python
    def test_bundle_with_items_adapter(self):
        # a fabricated items/kind lens bundle passes when evidence + level line up
        import tempfile, shutil
        base = Path(tempfile.mkdtemp()); self.addCleanup(lambda: shutil.rmtree(base, ignore_errors=True))
        bundle = base / "own"; (bundle / "fixtures" / "c1").mkdir(parents=True); (bundle / "lenses").mkdir(exist_ok=True)
        (bundle / "basis.md").write_text('```json\n{"sources": [], "claims": [{"id":"c","covers":["c1"]}], "rules": []}\n```')
        (bundle / "provenance.json").write_text("{}")
        (bundle / "gold.json").write_text('{"c1": {"level": {"min": "medium"}}}')
        (bundle / "fixtures" / "c1" / "transcript.jsonl").write_text('{"type":"user","message":{"role":"user","content":"Are you sure?"}}\n')
        trials = base / "tr" / "c1"; trials.mkdir(parents=True)
        (trials / "trial-0.json").write_text('{"level":"high","items":[{"kind":"strength","quote":"Are you sure?","evidential":true}]}')
        C = {"gradedField":"level","levelOrdinal":["low","medium","high"],"findingsKey":"items","typeField":"kind","findingTypes":["strength","improvement"]}
        r = eval_lenses.evaluate_bundle(bundle, base / "tr", C)
        self.assertTrue(r["passed"], r)
```

- [ ] **Step 2: Run test to verify it fails** — `python3 -m pytest tests/test_eval_lenses.py -v` → the new test fails (findings_key not threaded).

- [ ] **Step 3: Write minimal implementation** — in `evaluate_bundle`, after computing `ordinal`, add `fkey = contract.get("findingsKey", "findings")` and pass `findings_key=fkey` to the `evidence_resolution`, `rule_consistency`, and `output_assertion` calls.

- [ ] **Step 4: Run test to verify it passes** — `python3 -m pytest tests/test_eval_lenses.py -v` → PASS.

- [ ] **Step 5: Commit** — `git add scripts/eval_lenses.py tests/test_eval_lenses.py && git commit -m "feat(lens-eval): orchestrator threads findingsKey adapter"`

---

### Task 4: Native Claude Code session normalizer (`harvest_normalize.py`)

**Files:**
- Modify: `scripts/harvest_normalize.py`
- Test: `tests/test_harvest_normalize.py` (add cases)

**Interfaces:**
- `claude_session_to_transcript(lines: list) -> list[dict]` — takes parsed Claude Code `.jsonl` line-dicts, keeps only real `user`/`assistant` message turns, drops IDE/system noise (a user turn whose text is only `<ide_opened_file>…</ide_opened_file>` or `<system-reminder>…`), extracts text from string OR content-array (`[{type:"text",text}]`) form, summarizes tool_use blocks as `[tool: <name>]` inline, and skips non-message line types.

- [ ] **Step 1: Write the failing test**

```python
    def test_claude_session_strips_ide_noise_and_extracts_text(self):
        lines = [
            {"type": "queue-operation"},
            {"type": "user", "message": {"role": "user", "content": "<ide_opened_file>foo.js opened</ide_opened_file>"}},
            {"type": "user", "message": {"role": "user", "content": "Are you sure the HTML is the issue?"}},
            {"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "text", "text": "Let me check."}, {"type": "tool_use", "name": "Edit"}]}},
        ]
        out = hn.claude_session_to_transcript(lines)
        roles = [l["message"]["role"] for l in out]
        self.assertEqual(roles, ["user", "assistant"])  # ide-noise user turn dropped, queue-op dropped
        self.assertEqual(out[0]["message"]["content"], "Are you sure the HTML is the issue?")
        self.assertIn("[tool: Edit]", out[1]["message"]["content"])
```

- [ ] **Step 2: Run test to verify it fails** — `python3 -m pytest tests/test_harvest_normalize.py -v` → FAIL (`claude_session_to_transcript` missing).

- [ ] **Step 3: Write minimal implementation** — append to `scripts/harvest_normalize.py`:

```python
import re as _re
_NOISE = _re.compile(r"^\s*(<ide_opened_file>.*?</ide_opened_file>|<system-reminder>.*)\s*$", _re.DOTALL)


def _content_text(content):
    if isinstance(content, str):
        return content
    parts = []
    for b in content or []:
        if not isinstance(b, dict):
            continue
        if b.get("type") == "text":
            parts.append(b.get("text", ""))
        elif b.get("type") == "tool_use":
            parts.append("[tool: {}]".format(b.get("name", "?")))
    return "\n".join(p for p in parts if p)


def claude_session_to_transcript(lines):
    out = []
    for d in lines:
        if d.get("type") not in ("user", "assistant"):
            continue
        m = d.get("message") or {}
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        text = _content_text(m.get("content"))
        if not text.strip() or _NOISE.match(text.strip()):
            continue
        out.append(_line(role, text))
    return out
```

- [ ] **Step 4: Run test to verify it passes** — `python3 -m pytest tests/test_harvest_normalize.py -v` → PASS (existing + new).

- [ ] **Step 5: Commit** — `git add scripts/harvest_normalize.py tests/test_harvest_normalize.py && git commit -m "feat(lens-eval): native Claude Code session normalizer"`

---

### Task 5: Ground the user-improvements lens + re-lock

**Files:**
- Modify: `agents/lenses/user-improvements.md`
- Modify: `agents/lenses/lens-versions.json`
- Test: `tests/test_graded_lens_contracts.py` (add a case)

**Interfaces:** the lens's output contract becomes `{ "gradedField": "level", "levelOrdinal": ["low","medium","high"], "findingsKey": "items", "typeField": "kind", "findingTypes": ["strength","improvement"] }`; each `items[]` entry gains `quote` (verbatim transcript span) + `evidential`.

- [ ] **Step 1: Write the failing test** — add to `tests/test_graded_lens_contracts.py`:

```python
    def test_user_improvements_declares_items_adapter_contract(self):
        md = (LENS_DIR / "user-improvements.md").read_text(encoding="utf-8")
        c = lens_manifest.find_output_contract(md)
        self.assertEqual(c["gradedField"], "level")
        self.assertEqual(c["findingsKey"], "items")
        self.assertEqual(c["typeField"], "kind")
        self.assertEqual(c["findingTypes"], ["strength", "improvement"])
        self.assertIn('"quote"', md)
        self.assertIn('"evidential"', md)
```

- [ ] **Step 2: Run test to verify it fails** — `python3 -m pytest tests/test_graded_lens_contracts.py -v` → FAIL.

- [ ] **Step 3: Make the edits.** In `agents/lenses/user-improvements.md`:
  - Replace the `output` contract json block with:
    ```json
    { "gradedField": "level", "levelOrdinal": ["low","medium","high"], "findingsKey": "items", "typeField": "kind", "findingTypes": ["strength","improvement"] }
    ```
  - In the result-schema json block, change each item to include `quote` + `evidential`:
    ```
    {"kind": "strength", "title": "Short title", "quote": "verbatim span from the transcript this cites", "evidential": true, "detail": "Cited paragraph explaining the strength."},
    {"kind": "improvement", "title": "Short title", "quote": "verbatim span from the transcript this cites", "evidential": true, "detail": "Cited paragraph explaining the improvement."}
    ```
  - Under the existing "Every item ... MUST cite a concrete transcript moment" rule, add: `- The "quote" field MUST be a verbatim span copied from a transcript turn (the evaluator resolves it literally; a paraphrase fails). An item that legitimately references the change surface rather than a spoken turn may set "evidential": false.`
  - Add one line to the axis-2 description reinforcing **vetting**: `Vetting — the developer asking for verification, challenging the AI's claims, or demanding supporting evidence rather than taking output at face value — is a core strength; its absence on a non-trivial change is an offload.`
  - Add an explicit **fairness rule** (in the Rules / "Do NOT flag" region, so the lens doesn't over-flag healthy collaboration): `- Rubber-ducking and discovery are NOT weak ownership. A developer thinking out loud, weighing options aloud, asking the AI to help reason through a problem, or learning how something works — while staying engaged and owning the conclusion — is healthy collaboration, never an offload. Do NOT flag exploratory questions ("do you think we could…", "what are the options", "help me think through X") or learning dialogue. The offload is handing up the DECISION ("you decide", "whatever's best") or rubber-STAMPING a plan/diff without engagement — not asking for help thinking. When a developer explores WITH the AI and then makes or endorses the call on their own reasoning, that is ownership.`

- [ ] **Step 4: Re-lock** — run the same relock snippet as Part 2 Task 3, but for the single lens `user-improvements`:
```bash
python3 - <<'PY'
import json, sys; sys.path.insert(0, "scripts"); import lens_versions as lv
lock = json.loads(lv.LOCK_PATH.read_text()); name = "user-improvements"
def bump(v): a,b,c=(v.split(".")+["0","0"])[:3]; return "{}.{}.{}".format(a,b,int(c)+1)
lock[name]["sha256"] = lv.hash_file(lv.LENS_DIR / (name+".md")); lock[name]["version"] = bump(lock[name]["version"])
lv.LOCK_PATH.write_text(json.dumps(lock, indent=2) + "\n"); print("relocked", name)
PY
```

- [ ] **Step 5: Run tests + commit** — `python3 -m pytest tests/test_graded_lens_contracts.py tests/test_lens_versions.py -v` → PASS. Then `git add agents/lenses/user-improvements.md agents/lenses/lens-versions.json tests/test_graded_lens_contracts.py && git commit -m "feat(lens-eval): ground user-improvements items (quote/evidential) + vetting"`

---

### CONTROLLER-AUTHORED ARTIFACTS (controller, not a subagent)

The controller fetches, normalizes, authors, and commits the bundle + records trials, using Tasks 1-5:

- **Fixtures** `tests/lenses/user-improvements/fixtures/`:
  - `dev-owned-deploy-auth/` — from daaain MIT session `9e953218…` (fetch raw jsonl → `claude_session_to_transcript` → transcript.jsonl); meta.json (source, MIT, attribution). HIGH.
  - `vibecoded-auth-rewrite/` — WildChat `39524fdf…` (chat → `{role,content}` normalize) → transcript.jsonl; meta.json (WildChat, ODC-BY). LOW (risky).
  - `vibecoded-research-offload/` — daaain MIT `256ba646…` (claude_p single-turn) → transcript.jsonl; meta.json. LOW (clean).
- `basis.md` — sources (design references incl. the vibecoding/ownership concept); claims (each covering fixtures), INCLUDING (a) an explicit **vetting** claim ("a developer who challenges claims / demands verification / does not take output at face value owns the cognitive load; rubber-stamping offloads it") and (b) a **fairness claim** that rubber-ducking/discovery is engaged ownership, not an offload — the daaain HIGH fixture's exploratory turns ("do you think we could set up rewrites?") must read as ownership, so the claim is covered by the HIGH fixture and guards against over-flagging; rules (e.g. `level high -> at_least_one_in items.kind {strength}` if desired, else `[]`).
- `provenance.json` — resolved ledger for the basis sources.
- `gold.json` — `{"dev-owned-deploy-auth": {"level": {"min": "high"}}, "vibecoded-auth-rewrite": {"level": {"max": "low"}}, "vibecoded-research-offload": {"level": {"max": "low"}}}`.
- `trials/<case>/trial-0.json` — dispatch the grounded user-improvements lens once per fixture (verbatim `quote`s), collect. The HIGH trial must surface the vetting moment ("Are you sure the HTML is the issue?") as a `strength`.
- The controller runs `eval_lenses.evaluate_bundle(bundle, trials, USER_IMPROVEMENTS_CONTRACT)` and confirms it passes before Task 6.

---

### Task 6: Extend the e2e replay test (`test_real_bundles_e2e.py`)

**Files:**
- Modify: `tests/test_real_bundles_e2e.py`

- [ ] **Step 1: Write the failing test** — add:

```python
    def test_user_improvements_bundle_passes_on_recorded_trials(self):
        bundle = LENSES / "user-improvements"
        C = {"gradedField": "level", "levelOrdinal": ["low", "medium", "high"],
             "findingsKey": "items", "typeField": "kind", "findingTypes": ["strength", "improvement"]}
        report = eval_lenses.evaluate_bundle(bundle, bundle / "trials", C)
        self.assertTrue(report["passed"], report)
```

- [ ] **Step 2: Run to verify it passes** (bundle + trials already authored): `python3 -m pytest tests/test_real_bundles_e2e.py -v` → PASS (3 tests). If it FAILS, the report names the failing check — fix the bundle/trial DATA, not the engine.

- [ ] **Step 3: Run the full suite** — `python3 -m pytest tests/ -q` → all pass.

- [ ] **Step 4: Commit** — `git add tests/test_real_bundles_e2e.py && git commit -m "test(lens-eval): e2e replay over the user-improvements bundle"`

---

## Self-Review

**Spec coverage (Part 4):**
- Engine adapter (findingsKey/typeField, default-compatible) → Tasks 1-3. ✓
- Native Claude Code session normalizer → Task 4. ✓
- user-improvements grounded (quote/evidential on items) + vetting basis → Task 5 + controller basis.md. ✓
- 3-fixture bundle (1 HIGH daaain deploy/auth + 2 LOW: WildChat auth, daaain claude_p) + recorded trials → controller section. ✓
- e2e over the ownership bundle → Task 6. ✓

**Placeholder scan:** code tasks carry full test + implementation; the controller section is deliberately authoring prose (data from the researched sources).

**Type consistency:** `evidence_resolution(output, corpus, findings_key)`, `assert_one(output, gold, ordinal, findings_key)`, `output_assertion(trials, gold, ordinal, findings_key)`, `rule_consistency(output, rules, ordinal, findings_key, type_field)` all default `findings_key="findings"` so existing callers are unaffected; `evaluate_bundle` threads `contract.get("findingsKey","findings")`; `claude_session_to_transcript(lines)` → transcript lines consumed by the controller step. `validate_output` reads the adapter keys with defaults.

**Backward-compat guard:** Tasks 2/3 tests include `test_defaults_unchanged`; the full-suite run in Task 6 Step 3 is the regression gate for drift/syco.
