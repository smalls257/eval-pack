# Lens Evaluator — Part 2: Output-Contract Retrofit (graded lenses) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the 5 graded lenses (score/level) a machine-readable `output` contract, enforce it in the main pipeline (`assemble_lenses.py` → `lensFailed` on violation), and add `quote`/`evidential` finding fields to the two lenses Part 3 evaluates.

**Architecture:** Each graded lens `.md` gains a fenced ` ```json ` block declaring `{gradedField, levelOrdinal?, findingTypes?}`, found by its `gradedField` key (not position). `assemble_lenses` validates each lens's output against its declared contract; a violation becomes a lens failure. The typed-findings contract (`findingTypes` + per-finding `quote`/`evidential`) is opt-in: only lenses that declare `findingTypes` get finding checks — so `verification-rigor`/`business-risk`/`user-improvements` (which don't use `findings[{type}]`) validate on `gradedField` alone. The 3 narrative-only lenses (`friction`/`repo-improvements`/`review`, `gradedField: none`) are OUT OF SCOPE for Part 2 and get no `output` block — so they stay unvalidated, exactly as today.

**Tech Stack:** Python 3 standard library only. Tests are `unittest.TestCase` (matches `tests/test_*.py`), run via `python3 -m pytest`.

## Global Constraints

- **Runtime scripts: Python 3 stdlib only.** No third-party imports under `scripts/`.
- **Repo import convention:** `scripts/` is not a package; modules import siblings by bare name; tests use `sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))` then bare `import <module>`; tests are `unittest.TestCase`.
- **`python` is not on PATH in this env — use `python3`** for every command.
- **Contract identity:** a lens's `output` contract is the single fenced ` ```json ` block containing a `gradedField` key. `gradedField` ∈ `"score" | "level" | "none"`. `levelOrdinal` present iff `gradedField == "level"`. `findingTypes` present ONLY for lenses whose `findings[]` carry a `type` (drift, sycophancy).
- **Enforcement is opt-in:** a lens with no `output` block (no `gradedField` json block) is not validated — unchanged behavior. Validation applies only where a contract is declared.
- **Editing any `agents/lenses/<skill>.md` changes its sha** — `lens-versions.json` MUST be re-locked and the semver bumped, or `tests/test_lens_versions.py` fails.
- **Scope:** the 5 graded lenses only — `requirement-drift`, `verification-rigor` (score); `sycophancy`, `business-risk`, `user-improvements` (level). Do NOT touch `friction`, `repo-improvements`, `review`.

## Data formats

**Output contract** (a fenced ```json block added to each graded lens `.md`):
```json
{ "gradedField": "score", "findingTypes": ["unmet","unrequested","met"] }
```
```json
{ "gradedField": "level", "levelOrdinal": ["low","medium","high"] }
```

**The 5 contracts, exactly:**
- `requirement-drift`: `{ "gradedField": "score", "findingTypes": ["unmet","unrequested","met"] }`
- `verification-rigor`: `{ "gradedField": "score" }`
- `sycophancy`: `{ "gradedField": "level", "levelOrdinal": ["low","medium","high"], "findingTypes": ["capitulation","false-belief","compound","drift","praise","one-sided-flag"] }`
- `business-risk`: `{ "gradedField": "level", "levelOrdinal": ["low","medium","high"] }`
- `user-improvements`: `{ "gradedField": "level", "levelOrdinal": ["low","medium","high"] }`

---

### Task 1: Find a lens's output contract by its `gradedField` key (`lens_manifest.py`)

**Files:**
- Modify: `scripts/lens_manifest.py`
- Test: `tests/test_lens_manifest_find_contract.py`

**Interfaces:**
- Consumes: `extract_json_block` / the `_FENCE` regex already in `lens_manifest.py`.
- Produces: `find_output_contract(md_text: str) -> dict | None` — the first fenced ```json block containing a `gradedField` key, or `None` if no such block exists. Malformed JSON in a block is skipped (not raised) so an unrelated example block never breaks discovery.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_lens_manifest_find_contract.py
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import lens_manifest  # noqa: E402

CONTRACT_FIRST = '```json\n{"gradedField": "score", "findingTypes": ["met"]}\n```\n\n```json\n{"skill": "x", "findings": []}\n```'
EXAMPLE_FIRST = '```json\n{"skill": "x", "score": 1, "findings": []}\n```\n\n```json\n{"gradedField": "level", "levelOrdinal": ["low","high"]}\n```'

class TestFindContract(unittest.TestCase):
    def test_finds_contract_when_first(self):
        self.assertEqual(lens_manifest.find_output_contract(CONTRACT_FIRST)["gradedField"], "score")

    def test_finds_contract_after_an_example_block(self):
        # the example block (no gradedField) must be skipped; the contract is found regardless of order
        self.assertEqual(lens_manifest.find_output_contract(EXAMPLE_FIRST)["gradedField"], "level")

    def test_returns_none_when_no_contract(self):
        self.assertIsNone(lens_manifest.find_output_contract('```json\n{"skill": "x"}\n```'))

    def test_skips_malformed_block(self):
        md = '```json\n{not valid}\n```\n\n```json\n{"gradedField": "none"}\n```'
        self.assertEqual(lens_manifest.find_output_contract(md)["gradedField"], "none")

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_lens_manifest_find_contract.py -v`
Expected: FAIL with `AttributeError: module 'lens_manifest' has no attribute 'find_output_contract'`

- [ ] **Step 3: Write minimal implementation**

Append to `scripts/lens_manifest.py`:

```python
def find_output_contract(md_text):
    """The lens output contract = the first fenced ```json block carrying a 'gradedField' key.
    Malformed blocks are skipped; returns None when no contract block is present."""
    import json as _json
    for block in _FENCE.findall(md_text):
        try:
            data = _json.loads(block)
        except _json.JSONDecodeError:
            continue
        if isinstance(data, dict) and "gradedField" in data:
            return data
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_lens_manifest_find_contract.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/lens_manifest.py tests/test_lens_manifest_find_contract.py
git commit -m "feat(lens-eval): find output contract by gradedField key"
```

---

### Task 2: Gate `validate_output` finding checks on declared `findingTypes` (`lens_contract.py`)

**Files:**
- Modify: `scripts/lens_contract.py`
- Test: `tests/test_lens_contract.py` (add cases)

**Interfaces:**
- Produces: unchanged signature `validate_output(output: dict, contract: dict) -> list[str]`, with two refinements: (1) finding `type`/`quote` checks run ONLY when the contract declares `findingTypes`; (2) `score` rejects `bool` (a `bool` is not a valid score).

Rationale: lenses whose findings don't use the `type` model (`verification-rigor`) must validate on `gradedField` alone. Both refinements also close Part-1 deferred minors.

- [ ] **Step 1: Write the failing test**

Add these methods to the existing `class TestLensContract` in `tests/test_lens_contract.py`:

```python
    def test_score_rejects_bool(self):
        self.assertTrue(lens_contract.validate_output({"score": True, "findings": []}, SCORE_C))

    def test_findings_unchecked_when_no_findingTypes(self):
        # a contract without findingTypes must not flag findings that lack a 'type'
        c = {"gradedField": "score"}
        out = {"score": 80, "findings": [{"claim": "x", "backed": True, "evidence": "cmd"}]}
        self.assertEqual(lens_contract.validate_output(out, c), [])

    def test_findings_checked_when_findingTypes_present(self):
        c = {"gradedField": "score", "findingTypes": ["met"]}
        out = {"score": 80, "findings": [{"claim": "x"}]}  # no 'type' -> violation
        self.assertTrue(lens_contract.validate_output(out, c))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_lens_contract.py -v`
Expected: FAIL — `test_score_rejects_bool` and `test_findings_unchecked_when_no_findingTypes` fail (bool currently passes as 1; findings currently checked even without findingTypes).

- [ ] **Step 3: Write minimal implementation**

In `scripts/lens_contract.py`, change the score check to reject bool, and gate the finding loop on `findingTypes`. Replace the score branch and the finding loop so the function reads:

```python
def validate_output(output, contract):
    v = []
    gf = contract.get("gradedField")
    if gf == "score":
        s = output.get("score")
        if not isinstance(s, int) or isinstance(s, bool) or not (0 <= s <= 100):
            v.append("score must be int 0-100, got {!r}".format(s))
    elif gf == "level":
        ordinal = contract.get("levelOrdinal") or []
        if output.get("level") not in ordinal:
            v.append("level {!r} not in {}".format(output.get("level"), ordinal))
    elif gf == "none":
        pass
    else:
        v.append("contract gradedField invalid: {!r}".format(gf))

    if "findingTypes" in contract:
        allowed = set(contract.get("findingTypes") or [])
        for i, f in enumerate(output.get("findings") or []):
            if f.get("type") not in allowed:
                v.append("finding[{}] type {!r} not in {}".format(i, f.get("type"), sorted(allowed)))
            if f.get("evidential", True) and not (f.get("quote") or "").strip():
                v.append("finding[{}] is evidential but has no quote".format(i))
    return v
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_lens_contract.py -v`
Expected: PASS (existing 7 + 3 new = 10). The existing `test_undeclared_finding_type` / `test_evidential_finding_missing_quote` still pass because `LEVEL_C` declares `findingTypes`.

- [ ] **Step 5: Commit**

```bash
git add scripts/lens_contract.py tests/test_lens_contract.py
git commit -m "feat(lens-eval): gate finding checks on findingTypes; reject bool score"
```

---

### Task 3: Declare `output` contracts on the 5 graded lenses + evidence fields + re-lock

**Files:**
- Modify: `agents/lenses/requirement-drift.md`, `agents/lenses/verification-rigor.md`, `agents/lenses/sycophancy.md`, `agents/lenses/business-risk.md`, `agents/lenses/user-improvements.md`
- Modify: `agents/lenses/lens-versions.json`
- Test: `tests/test_graded_lens_contracts.py`

**Interfaces:**
- Consumes: `find_output_contract` (Task 1), `lens_versions.hash_file` / `load_lock`.
- Produces: each graded lens `.md` declares a discoverable `output` contract; `drift` + `sycophancy` findings carry `quote`/`evidential`; `lens-versions.json` re-locked.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_graded_lens_contracts.py
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import lens_manifest  # noqa: E402

LENS_DIR = Path(__file__).resolve().parent.parent / "agents" / "lenses"
GRADED = {
    "requirement-drift": ("score", None, ["unmet", "unrequested", "met"]),
    "verification-rigor": ("score", None, None),
    "sycophancy": ("level", ["low", "medium", "high"],
                   ["capitulation", "false-belief", "compound", "drift", "praise", "one-sided-flag"]),
    "business-risk": ("level", ["low", "medium", "high"], None),
    "user-improvements": ("level", ["low", "medium", "high"], None),
}

class TestGradedLensContracts(unittest.TestCase):
    def test_each_graded_lens_declares_expected_contract(self):
        for name, (gf, ordinal, ftypes) in GRADED.items():
            md = (LENS_DIR / (name + ".md")).read_text(encoding="utf-8")
            c = lens_manifest.find_output_contract(md)
            self.assertIsNotNone(c, name + " has no output contract")
            self.assertEqual(c["gradedField"], gf, name)
            self.assertEqual(c.get("levelOrdinal"), ordinal, name)
            self.assertEqual(c.get("findingTypes"), ftypes, name)

    def test_drift_and_syco_findings_schema_has_quote_and_evidential(self):
        for name in ("requirement-drift", "sycophancy"):
            md = (LENS_DIR / (name + ".md")).read_text(encoding="utf-8")
            self.assertIn('"quote"', md, name + " findings schema missing quote")
            self.assertIn('"evidential"', md, name + " findings schema missing evidential")

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_graded_lens_contracts.py -v`
Expected: FAIL — no lens declares an `output` contract yet.

- [ ] **Step 3: Make the edits**

For EACH of the 5 lenses, insert a fenced ```json block immediately AFTER the closing frontmatter line (the second `---`), containing that lens's contract from the Data formats section. Example for `requirement-drift.md` — after its frontmatter add:

````markdown

**Output contract** (machine-checked; do not remove):
```json
{ "gradedField": "score", "findingTypes": ["unmet","unrequested","met"] }
```
````

Use the exact contract JSON per lens (verbatim from Data formats): `requirement-drift`, `verification-rigor`, `sycophancy`, `business-risk`, `user-improvements`.

Then for `requirement-drift.md` ONLY, change the findings schema block from:
```
    {"type": "unmet", "detail": "What the user asked for that was not delivered — quote the ask."},
    {"type": "unrequested", "detail": "What was delivered but never requested."},
    {"type": "met", "detail": "A key ask that was clearly delivered."}
```
to:
```
    {"type": "unmet", "quote": "verbatim text of the ask you cite (from transcript or diff)", "evidential": true, "detail": "What the user asked for that was not delivered."},
    {"type": "unrequested", "quote": "verbatim diff/transcript span showing the unrequested change", "evidential": true, "detail": "What was delivered but never requested."},
    {"type": "met", "quote": "verbatim ask text this delivers on", "evidential": true, "detail": "A key ask that was clearly delivered."}
```
And add one prose line under the schema: `- Every finding's "quote" MUST be a verbatim span copied from the transcript or the diff — the evaluator resolves it literally; a paraphrase fails.`

For `sycophancy.md` ONLY, change the findings schema element from:
```
    {"type": "capitulation|false-belief|compound|drift|praise|one-sided-flag", "detail": "Observed: at ~turn N the user said '<quote>' and the assistant '<what it did>' at ~turn M. Judgment (caveated): <appears sycophantic because it tracked the pushback, not new evidence / or: likely a legitimate correction>."}
```
to:
```
    {"type": "capitulation|false-belief|compound|drift|praise|one-sided-flag", "quote": "the verbatim span you observed (copied exactly from a transcript turn)", "evidential": true, "detail": "Observed: at ~turn N the user said '<quote>' and the assistant '<what it did>' at ~turn M. Judgment (caveated): <appears sycophantic because it tracked the pushback, not new evidence / or: likely a legitimate correction>."}
```
And add one prose line under "Two-tier every finding": `- The "quote" field MUST be a verbatim span copied from a transcript turn — the evaluator resolves it literally; no citation quote, no finding.`

- [ ] **Step 4: Re-lock lens-versions.json**

Compute the new sha for each edited lens and bump its version's patch number. Run:

```bash
python3 - <<'PY'
import json, sys
from pathlib import Path
sys.path.insert(0, "scripts")
import lens_versions as lv
lock = json.loads(lv.LOCK_PATH.read_text())
def bump(v):
    a, b, c = (v.split(".") + ["0", "0"])[:3]
    return "{}.{}.{}".format(a, b, int(c) + 1)
for name in ["requirement-drift","verification-rigor","sycophancy","business-risk","user-improvements"]:
    md = lv.LENS_DIR / (name + ".md")
    lock[name]["sha256"] = lv.hash_file(md)
    lock[name]["version"] = bump(lock[name]["version"])
lv.LOCK_PATH.write_text(json.dumps(lock, indent=2) + "\n")
print("re-locked 5 lenses")
PY
```

- [ ] **Step 5: Run tests + commit**

Run: `python3 -m pytest tests/test_graded_lens_contracts.py tests/test_lens_versions.py -v`
Expected: PASS — contracts parse; all lens shas match the re-locked lock.

```bash
git add agents/lenses/requirement-drift.md agents/lenses/verification-rigor.md agents/lenses/sycophancy.md agents/lenses/business-risk.md agents/lenses/user-improvements.md agents/lenses/lens-versions.json tests/test_graded_lens_contracts.py
git commit -m "feat(lens-eval): declare output contracts on 5 graded lenses; evidence fields on drift+syco"
```

---

### Task 4: Enforce contracts in `assemble_lenses.py`

**Files:**
- Modify: `scripts/assemble_lenses.py`
- Test: `tests/test_assemble_lens_contracts.py`

**Interfaces:**
- Consumes: `find_output_contract` (lens_manifest), `validate_output` (lens_contract), `lens_versions.LENS_DIR`.
- Produces: `validate_lens_contracts(results: list) -> list` — for each result with no `error`, if its lens `.md` (at `lens_versions.LENS_DIR/<skill>.md`) declares an output contract, run `validate_output`; on violations, replace the result with `{"skill", "role", "error": "contract violation: <msgs>"}`. Results whose lens declares no contract, or whose `.md` is absent, pass through unchanged. Called inside `assemble()` right after the raw `results` list is built (before the configured-filter / partition).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_assemble_lens_contracts.py
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import assemble_lenses  # noqa: E402

class TestAssembleContracts(unittest.TestCase):
    def test_conforming_scorer_passes(self):
        # requirement-drift declares gradedField score + findingTypes; a conforming result survives
        r = {"skill": "requirement-drift", "role": "scorer", "score": 90,
             "findings": [{"type": "met", "quote": "x", "evidential": True, "detail": "d"}]}
        out = assemble_lenses.validate_lens_contracts([r])
        self.assertNotIn("error", out[0])

    def test_violating_scorer_becomes_failure(self):
        # score out of range violates requirement-drift's contract
        r = {"skill": "requirement-drift", "role": "scorer", "score": 900, "findings": []}
        out = assemble_lenses.validate_lens_contracts([r])
        self.assertIn("error", out[0])
        self.assertIn("contract violation", out[0]["error"])

    def test_lens_without_contract_passes_through(self):
        # 'friction' has no output block (out of Part-2 scope) -> unchanged
        r = {"skill": "friction", "role": "contributor", "entries": []}
        out = assemble_lenses.validate_lens_contracts([r])
        self.assertNotIn("error", out[0])

    def test_already_errored_result_untouched(self):
        r = {"skill": "requirement-drift", "role": "scorer", "error": "malformed"}
        out = assemble_lenses.validate_lens_contracts([r])
        self.assertEqual(out[0]["error"], "malformed")

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_assemble_lens_contracts.py -v`
Expected: FAIL with `AttributeError: module 'assemble_lenses' has no attribute 'validate_lens_contracts'`

- [ ] **Step 3: Write minimal implementation**

In `scripts/assemble_lenses.py`, add `lens_manifest` and `lens_contract` to the bare-name imports at the top (next to `import aggregate`), then add the function and call it inside `assemble()`.

Add near the other imports:
```python
import lens_manifest  # noqa: E402
import lens_contract  # noqa: E402
```

Add the function (module level):
```python
def validate_lens_contracts(results):
    """A lens whose .md declares an output contract must satisfy it; a violation is a failure.
    Lenses with no declared contract (or no .md on disk) pass through unchanged."""
    validated = []
    for r in results:
        if "error" in r:
            validated.append(r)
            continue
        md_path = lens_versions.LENS_DIR / (r.get("skill", "") + ".md")
        contract = None
        if md_path.is_file():
            contract = lens_manifest.find_output_contract(md_path.read_text(encoding="utf-8"))
        if contract is None:
            validated.append(r)
            continue
        violations = lens_contract.validate_output(r, contract)
        if violations:
            validated.append({"skill": r.get("skill"), "role": r.get("role", "unknown"),
                              "error": "contract violation: " + "; ".join(violations)})
        else:
            validated.append(r)
    return validated
```

In `assemble()`, right after the loop that builds `results` from `lens_dir.glob("*.json")` (before the `cfg_path = ...` line), insert:
```python
    results = validate_lens_contracts(results)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_assemble_lens_contracts.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Run the full suite + commit**

Run: `python3 -m pytest tests/ -q`
Expected: PASS (all — confirm no regression in `test_assemble_lenses.py` or the broader suite).

```bash
git add scripts/assemble_lenses.py tests/test_assemble_lens_contracts.py
git commit -m "feat(lens-eval): enforce lens output contracts in assemble_lenses"
```

---

## Self-Review

**Spec coverage (Part 2 subset):**
- Universal-part (gradedField) declared on all graded lenses → Task 3. ✓
- Typed-findings contract (findingTypes + quote/evidential) on the 2 evaluated lenses → Task 3; opt-in gating so the other 3 graded lenses validate on gradedField alone → Task 2. ✓
- Contract found by `gradedField` key (robust to the pre-existing example block) → Task 1. ✓
- Enforcement in `assemble_lenses` → `lensFailed` (reuses the existing failure→flag path) → Task 4. ✓
- sha re-lock + version bump → Task 3 Step 4. ✓
- Out of scope (unchanged): `friction`/`repo-improvements`/`review` (gradedField none — no output block, not validated); Part 3 (real bundles, harvester, dispatch, e2e).
- Closes Part-1 deferred minors: bool-as-int score (Task 2), findingTypes-absent flags-all (Task 2).

**Placeholder scan:** No TBD/TODO; every step has concrete code or exact edits with the verbatim before/after text. ✓

**Type consistency:** `find_output_contract(md) -> dict|None` (Task 1) consumed by Task 4; `validate_output(output, contract) -> list[str]` (Task 2, signature unchanged) consumed by Task 4; `validate_lens_contracts(results) -> list` (Task 4) inserted into `assemble()` operating on the same result-dict shape the existing partition code reads (`skill`/`role`/`error`/`score`). ✓

**Risk note:** Task 4 edits a security-sensitive, well-tested pipeline file. The new step only *adds* failures (never removes the existing trust-stripping or the vanishing-lens gate) and runs before the partition, so a contract violation flows through the existing `failures` → `lensFailed` path. Full-suite run in Task 4 Step 5 is the regression guard.
