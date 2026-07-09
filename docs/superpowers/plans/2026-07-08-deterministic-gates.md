# Deterministic Gates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert every instruction-level promise in the eval-pack customization surface into a deterministic, code-enforced gate — and close the adversarial findings (cosmetic lens verdict, vanishing lenses, undiscoverable surface, unverifiable prompt knobs).

**Architecture (the governing principle, from the user):** *We don't trust LLMs; we trust the harness and validation. Anything without a deterministic stop/gate is assumed broken.* Concretely: LLM-produced artifacts (analysis.json, test-results.json, lens outputs) are validated by scripts against the resolved config; violations HALT (or surface as red flags) via code paths that always run. Lens verdict influence flows through the already-tested `patterns.json` flags → `renderVerdict` pipeline (Python emits flags; the banner triage is existing, covered code). `render_html.py` is the backstop gate — it refuses to render a non-conforming pack even if the orchestrating LLM skips a step.

**Tech Stack:** Python 3 stdlib only (no pip; CI `python -m unittest`, Windows-safe; machine has `python3`, NOT `python`). Node built-in test runner for pure JS functions (existing `tests/*.test.mjs` pattern — DOM-free functions exported via `module.exports`).

**Working directory:** `/Users/jasonsmith/Code/eval-pack-config-foundation` (worktree, branch `feat/config-foundation`).

**Standing rules for every task:** line numbers are hints — match by content; run the touched test module AND the full suite (`python3 -m unittest discover -s tests -p "test_*.py"`) before committing; append trailer `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` to every commit; if real code contradicts the plan beyond drift, report NEEDS_CONTEXT instead of improvising.

---

### Task 1: Lens completeness gate + lens verdict flags (findings #1, #2)

`assemble_lenses.py` must (a) cross-check configured lenses against produced outputs — a configured lens with no output file becomes a recorded **failure**, never a silent absence; (b) emit deterministic flags into `patterns.json` so lens results reach the verdict banner through the existing tested flag triage: any lens failure → **red** flag; `finalScore < coreScore` → **amber** flag showing the math.

**Files:**
- Modify: `scripts/assemble_lenses.py`
- Test: `tests/test_assemble_lenses.py` (append)

- [ ] **Step 1: Write the failing tests — append to `tests/test_assemble_lenses.py` before `if __name__` (or at EOF if no guard):**

```python
class TestLensGates(unittest.TestCase):
    def _cfg(self, d, lenses, rule="min"):
        import config
        base = dict(json.loads(json.dumps(config.DEFAULTS)))
        base["analysisLenses"] = lenses
        base["verdictAggregation"] = rule
        (Path(d) / "eval-config.json").write_text(json.dumps(base), encoding="utf-8")

    def test_configured_but_missing_lens_is_failure(self):
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d)
            (pack / "lenses").mkdir()
            (pack / "analysis.json").write_text(
                json.dumps({"highlights": {"confidencePercent": 90}}), encoding="utf-8")
            self._cfg(d, [{"skill": "ghost-lens", "role": "scorer"}])
            out = assemble_lenses.assemble(d)
            self.assertTrue(any(f.get("skill") == "ghost-lens" and "no output" in f.get("error", "")
                                for f in out["failures"]))

    def test_failure_emits_red_flag_into_patterns(self):
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d)
            (pack / "lenses").mkdir()
            (pack / "analysis.json").write_text(
                json.dumps({"highlights": {"confidencePercent": 90}}), encoding="utf-8")
            (pack / "patterns.json").write_text(json.dumps({"flags": []}), encoding="utf-8")
            self._cfg(d, [{"skill": "ghost-lens", "role": "scorer"}])
            out = assemble_lenses.assemble(d)
            assemble_lenses.write_outputs(d, out)
            patterns = json.loads((pack / "patterns.json").read_text(encoding="utf-8"))
            self.assertTrue(any(f["id"] == "lensFailed" and f["level"] == "red"
                                and "ghost-lens" in f["label"] for f in patterns["flags"]))

    def test_low_finalscore_emits_amber_flag_with_math(self):
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d)
            (pack / "lenses").mkdir()
            (pack / "lenses" / "perf.json").write_text(
                json.dumps({"skill": "perf", "role": "scorer", "score": 61, "rationale": "slow"}),
                encoding="utf-8")
            (pack / "analysis.json").write_text(
                json.dumps({"highlights": {"confidencePercent": 90}}), encoding="utf-8")
            (pack / "patterns.json").write_text(json.dumps({"flags": []}), encoding="utf-8")
            self._cfg(d, [{"skill": "perf", "role": "scorer"}])
            out = assemble_lenses.assemble(d)
            assemble_lenses.write_outputs(d, out)
            patterns = json.loads((pack / "patterns.json").read_text(encoding="utf-8"))
            flag = next(f for f in patterns["flags"] if f["id"] == "lensVerdict")
            self.assertEqual(flag["level"], "amber")
            self.assertIn("61", flag["label"])
            self.assertIn("90", flag["label"])

    def test_no_lenses_configured_no_flags_added(self):
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d)
            (pack / "analysis.json").write_text(
                json.dumps({"highlights": {"confidencePercent": 90}}), encoding="utf-8")
            (pack / "patterns.json").write_text(json.dumps({"flags": []}), encoding="utf-8")
            self._cfg(d, [])
            out = assemble_lenses.assemble(d)
            assemble_lenses.write_outputs(d, out)
            patterns = json.loads((pack / "patterns.json").read_text(encoding="utf-8"))
            self.assertEqual(patterns["flags"], [])  # Airplane Test: zero lenses = untouched
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m unittest tests.test_assemble_lenses -v`
Expected: FAIL (`write_outputs` undefined; missing-lens not in failures).

- [ ] **Step 3: Implement in `scripts/assemble_lenses.py`**

Inside `assemble(pack_dir)`, after the `results` list is built from `lens_dir.glob`, add the cross-check (needs `cfg` — move the existing cfg-loading lines ABOVE the contributor/scorer filtering so `cfg` is available):

```python
    # Deterministic gate: a configured lens with no output file is a FAILURE, not an absence.
    # The orchestrator is an LLM; prose promises don't count. (finding: vanishing lens)
    produced = {r.get("skill") for r in results}
    for lens in cfg.get("analysisLenses") or []:
        skill = lens.get("skill")
        if skill and skill not in produced:
            results.append({"skill": skill, "role": lens.get("role", "unknown"),
                            "error": "configured lens produced no output"})
```

Then REPLACE the module's `main()` write with a `write_outputs` function and call it from `main` (keep the CLI behavior; the split makes the flag-append testable):

```python
def _lens_flags(out):
    """Deterministic flags for the verdict banner (rides the tested patterns pipeline)."""
    flags = []
    for f in out.get("failures", []):
        flags.append({"id": "lensFailed", "level": "red",
                      "label": "Lens failed: {} ({})".format(
                          f.get("skill", "?"), f.get("error", "error"))})
    core, final = out.get("coreScore"), out.get("finalScore")
    if final is not None and core is not None and final < core:
        flags.append({"id": "lensVerdict", "level": "amber",
                      "label": "Lens verdict: final {:g} ({} of core {:g} and {} scorer(s))".format(
                          final, out.get("rule"), core, len(out.get("scorers", [])))})
    return flags


def write_outputs(pack_dir, out):
    """Write lenses.json and append lens flags into patterns.json (never crash the eval)."""
    pack = Path(pack_dir)
    (pack / "lenses.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    new_flags = _lens_flags(out)
    if not new_flags:
        return
    ppath = pack / "patterns.json"
    try:
        patterns = json.loads(ppath.read_text(encoding="utf-8")) if ppath.is_file() else {"flags": []}
    except json.JSONDecodeError:
        patterns = {"flags": []}
    existing = patterns.setdefault("flags", [])
    # idempotent on re-run: drop prior lens flags before appending
    patterns["flags"] = [f for f in existing if f.get("id") not in ("lensFailed", "lensVerdict")] + new_flags
    ppath.write_text(json.dumps(patterns, indent=2), encoding="utf-8")
```

Update `main()` to call `out = assemble(args.pack_dir)` then `write_outputs(args.pack_dir, out)` (replacing its direct `lenses.json` write; keep the summary print).

- [ ] **Step 4: Run tests + full suite** — `python3 -m unittest tests.test_assemble_lenses -v` then the full suite. All green (existing assemble tests call `assemble()` only — unchanged return shape).

- [ ] **Step 5: Commit** — `git add scripts/assemble_lenses.py tests/test_assemble_lenses.py && git commit -m "feat(lenses): deterministic gates — missing lens is a failure; lens results flag the verdict"`

---

### Task 2: Lens rendering — finalScore in the confidence card, tolerant finding shapes (findings #1-display, #6, #9)

Pure-function extraction so the logic is node-testable (existing `module.exports` pattern): `effectiveConfidence(analysis, lenses)` and `lensFindingText(f)`.

**Files:**
- Modify: `templates/html/scripts.js`
- Test: `tests/lens-render.test.mjs` (new)

- [ ] **Step 1: Write the failing test — create `tests/lens-render.test.mjs`:**

```javascript
import { test } from 'node:test';
import assert from 'node:assert';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
global.window = { __EVAL_PACK_TEST__: true };
const { effectiveConfidence, lensFindingText } = require('../templates/html/scripts.js');

test('effectiveConfidence uses finalScore when a non-core rule ran scorers', () => {
  const analysis = { highlights: { confidencePercent: 90 } };
  const lenses = { rule: 'min', coreScore: 90, finalScore: 61, scorers: [{ skill: 'x', score: 61 }] };
  assert.deepStrictEqual(effectiveConfidence(analysis, lenses),
    { value: 61, note: 'min of core 90 and 1 scorer lens(es)' });
});

test('effectiveConfidence falls back to core when no scorers or rule core', () => {
  const analysis = { highlights: { confidencePercent: 90 } };
  assert.deepStrictEqual(effectiveConfidence(analysis, null), { value: 90, note: null });
  assert.deepStrictEqual(
    effectiveConfidence(analysis, { rule: 'core', coreScore: 90, scorers: [] }),
    { value: 90, note: null });
});

test('lensFindingText handles strings and {type,detail} objects', () => {
  assert.strictEqual(lensFindingText('plain finding'), 'plain finding');
  assert.strictEqual(lensFindingText({ type: 'unmet', detail: 'missed the ask' }),
    'unmet: missed the ask');
  assert.strictEqual(lensFindingText({ detail: 'just detail' }), 'just detail');
  assert.strictEqual(lensFindingText(42), '42');
});
```

- [ ] **Step 2: Run to verify failure** — `node --test tests/lens-render.test.mjs` → FAIL (not exported).

- [ ] **Step 3: Implement in `templates/html/scripts.js`**

a) Add the two pure functions near `lensScore` (which already exists):

```javascript
// Verdict-facing confidence: when scorer lenses ran under a non-core rule, the aggregated
// finalScore IS the confidence a user should lead with (finding: cosmetic finalScore).
function effectiveConfidence(analysis, lenses) {
  const core = ((analysis || {}).highlights || {}).confidencePercent;
  const l = lenses || {};
  const scorers = l.scorers || [];
  if (l.rule && l.rule !== 'core' && scorers.length && l.finalScore != null) {
    return { value: l.finalScore,
             note: `${l.rule} of core ${l.coreScore} and ${scorers.length} scorer lens(es)` };
  }
  return { value: core != null ? core : null, note: null };
}

// A lens finding may be a plain string or {type, detail} — render both, never [object Object].
function lensFindingText(f) {
  if (typeof f === 'string') return f;
  if (f && typeof f === 'object') {
    const detail = f.detail != null ? String(f.detail) : '';
    return f.type ? `${f.type}: ${detail}` : detail || JSON.stringify(f);
  }
  return String(f);
}
```

b) In `renderHighlights`, the confidence card reads `h.confidencePercent` (`const pct = h.confidencePercent;`). Change `renderHighlights(analysis)` to `renderHighlights(analysis, lenses)` and the pct line to:

```javascript
  const eff = effectiveConfidence(analysis, lenses);
  const pct = eff.value;
```

and after the `confNotes.textContent = h.confidenceNotes || '';` line, append the lens note when present:

```javascript
    if (confNotes && eff.note) confNotes.textContent =
      (h.confidenceNotes ? h.confidenceNotes + ' — ' : '') + eff.note;
```

Update the call site in `renderSession`: `renderHighlights(analysis, data.lenses);`

c) In `renderLenses`, use `lensFindingText` for contributor findings and render scorer findings too. Replace the contributor/scorer card bodies:

```javascript
  (lenses.scorers || []).forEach(s => {
    const findings = (s.findings || []).map(f => html`<li>${lensFindingText(f)}</li>`).join('');
    parts.push(html`<div class="lens-card"><div class="lens-meta">scorer · ${s.skill}</div><p>score <strong>${lensScore(s.score)}</strong> — ${s.rationale}</p>${safe(findings ? html`<ul>${safe(findings)}</ul>` : '')}</div>`);
  });
  (lenses.contributors || []).forEach(c => {
    const findings = (c.findings || []).map(f => html`<li>${lensFindingText(f)}</li>`).join('');
    parts.push(html`<div class="lens-card"><div class="lens-meta">contributor · ${c.skill}</div><h4>${c.title}</h4><ul>${safe(findings)}</ul></div>`);
  });
```

d) Append `effectiveConfidence` and `lensFindingText` to the existing `module.exports` object at the bottom of the file.

- [ ] **Step 4: Run** — `node --test tests/lens-render.test.mjs tests/cost.test.mjs tests/lightbox-helpers.test.mjs` → all pass; `node --check templates/html/scripts.js` clean; full Python suite still green.

- [ ] **Step 5: Commit** — `git add templates/html/scripts.js tests/lens-render.test.mjs && git commit -m "feat(lenses): confidence card leads with finalScore; findings render for both roles"`

---

### Task 3: Contract validator — deterministic checks on LLM-produced artifacts (findings #4, RS-CMD proof)

New `scripts/validate_contracts.py`: validates `analysis.json` and `test-results.json` against the resolved config. Pure collection function + CLI. This is the code that replaces trust.

**Files:**
- Create: `scripts/validate_contracts.py`
- Test: `tests/test_validate_contracts.py`

- [ ] **Step 1: Write the failing tests — create `tests/test_validate_contracts.py`:**

```python
# tests/test_validate_contracts.py
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import validate_contracts  # noqa: E402
import config  # noqa: E402


def _pack(d, cfg_over=None, analysis=None, test_results=None):
    pack = Path(d)
    base = dict(json.loads(json.dumps(config.DEFAULTS)))
    base.update(cfg_over or {})
    (pack / "eval-config.json").write_text(json.dumps(base), encoding="utf-8")
    if analysis is not None:
        (pack / "analysis.json").write_text(json.dumps(analysis), encoding="utf-8")
    if test_results is not None:
        (pack / "test-results.json").write_text(json.dumps(test_results), encoding="utf-8")
    return pack


class TestFrictionContract(unittest.TestCase):
    def test_offlist_friction_type_is_gap(self):
        with tempfile.TemporaryDirectory() as d:
            _pack(d, {"frictionCategories": ["tooling", "docs"]},
                  analysis={"title": "t", "frictionLog": [{"friction": "x", "type": "vibes"}]})
            gaps = validate_contracts.collect_gaps(d)
            self.assertTrue(any("frictionLog" in g and "vibes" in g for g in gaps))

    def test_onlist_type_ok(self):
        with tempfile.TemporaryDirectory() as d:
            _pack(d, {"frictionCategories": ["tooling", "docs"]},
                  analysis={"title": "t", "frictionLog": [{"friction": "x", "type": "docs"}]})
            self.assertEqual(validate_contracts.collect_gaps(d), [])


class TestRetrospectiveContract(unittest.TestCase):
    def test_missing_answer_is_gap(self):
        with tempfile.TemporaryDirectory() as d:
            _pack(d, {"retrospectiveQuestions": ["Q1?", "Q2?"]},
                  analysis={"title": "t", "retrospectiveAnswers": [
                      {"question": "Q1?", "answer": "a"}]})
            gaps = validate_contracts.collect_gaps(d)
            self.assertTrue(any("Q2?" in g for g in gaps))

    def test_all_answered_ok(self):
        with tempfile.TemporaryDirectory() as d:
            _pack(d, {"retrospectiveQuestions": ["Q1?"]},
                  analysis={"title": "t", "retrospectiveAnswers": [
                      {"question": "Q1?", "answer": "a"}]})
            self.assertEqual(validate_contracts.collect_gaps(d), [])


class TestRubricContract(unittest.TestCase):
    def test_missing_or_unknown_band_is_gap(self):
        with tempfile.TemporaryDirectory() as d:
            _pack(d, {"rubric": {"high": "ship it", "low": "block"}},
                  analysis={"title": "t"})
            self.assertTrue(any("rubricApplied" in g for g in validate_contracts.collect_gaps(d)))
        with tempfile.TemporaryDirectory() as d:
            _pack(d, {"rubric": {"high": "ship it"}},
                  analysis={"title": "t", "rubricApplied": {"band": "banana", "why": "w"}})
            self.assertTrue(any("banana" in g for g in validate_contracts.collect_gaps(d)))

    def test_valid_band_ok(self):
        with tempfile.TemporaryDirectory() as d:
            _pack(d, {"rubric": {"high": "ship it"}},
                  analysis={"title": "t", "rubricApplied": {"band": "high", "why": "w"}})
            self.assertEqual(validate_contracts.collect_gaps(d), [])


class TestTestCommandContract(unittest.TestCase):
    def test_commands_must_match_and_verdict_consistent(self):
        with tempfile.TemporaryDirectory() as d:
            _pack(d, {"testCommands": ["cmd-a", "cmd-b"]},
                  analysis={"title": "t"},
                  test_results={"verdict": "pass",
                                "commands": [{"command": "cmd-a", "exitCode": 0},
                                             {"command": "cmd-b", "exitCode": 1}]})
            gaps = validate_contracts.collect_gaps(d)
            self.assertTrue(any("verdict" in g for g in gaps))  # exit 1 but verdict pass
        with tempfile.TemporaryDirectory() as d:
            _pack(d, {"testCommands": ["cmd-a"]},
                  analysis={"title": "t"},
                  test_results={"verdict": "fail", "commands": [{"command": "other", "exitCode": 1}]})
            gaps = validate_contracts.collect_gaps(d)
            self.assertTrue(any("cmd-a" in g for g in gaps))  # configured command not proven run

    def test_conforming_run_ok(self):
        with tempfile.TemporaryDirectory() as d:
            _pack(d, {"testCommands": ["cmd-a"]},
                  analysis={"title": "t"},
                  test_results={"verdict": "pass", "commands": [{"command": "cmd-a", "exitCode": 0}]})
            self.assertEqual(validate_contracts.collect_gaps(d), [])


class TestDisabledAnalysisSkips(unittest.TestCase):
    def test_disabled_stub_skips_analysis_contracts(self):
        with tempfile.TemporaryDirectory() as d:
            _pack(d, {"retrospectiveQuestions": ["Q1?"], "rubric": {"h": "x"}},
                  analysis={"title": "disabled", "disabled": True})
            self.assertEqual(validate_contracts.collect_gaps(d), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure** — `python3 -m unittest tests.test_validate_contracts -v` → FAIL (no module).

- [ ] **Step 3: Create `scripts/validate_contracts.py`:**

```python
#!/usr/bin/env python3
"""Deterministic contract gates for LLM-produced pack artifacts.

Principle: we don't trust LLMs — we trust validation. The evaluator and the
orchestrating skill PROMISE to honor the resolved config (friction taxonomy,
retrospective questions, rubric, test commands); this script CHECKS. A violation
is a gap that halts the pipeline (the skill re-dispatches once, then stops), and
render_html refuses to render a non-conforming pack as the code-level backstop.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))  # noqa: E402
import config  # noqa: E402


def _read(pack, name):
    p = Path(pack) / name
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def collect_gaps(pack_dir):
    """Return a list of human-readable contract violations; empty means conforming."""
    gaps = []
    cfg_data = _read(pack_dir, "eval-config.json")
    cfg = cfg_data if cfg_data is not None else config.read_config()
    analysis = _read(pack_dir, "analysis.json") or {}
    results = _read(pack_dir, "test-results.json") or {}

    if not analysis.get("disabled"):
        # frictionLog types must come from the configured taxonomy.
        cats = set(cfg.get("frictionCategories") or [])
        if cats:
            for i, item in enumerate(analysis.get("frictionLog") or []):
                t = item.get("type")
                if t not in cats:
                    gaps.append(
                        "frictionLog[{}].type {!r} is not in frictionCategories {}".format(
                            i, t, sorted(cats)))
        # every configured retrospective question must be answered, verbatim-keyed.
        questions = cfg.get("retrospectiveQuestions") or []
        if questions:
            answered = {a.get("question") for a in analysis.get("retrospectiveAnswers") or []
                        if a.get("answer")}
            for q in questions:
                if q not in answered:
                    gaps.append("retrospectiveAnswers missing an answer for: {!r}".format(q))
        # a configured rubric must be applied to a real band.
        rubric = cfg.get("rubric") or {}
        if rubric:
            applied = analysis.get("rubricApplied") or {}
            band = applied.get("band")
            if not band:
                gaps.append("rubricApplied missing: config sets a rubric but analysis names no band")
            elif band not in rubric:
                gaps.append("rubricApplied.band {!r} is not a configured rubric band {}".format(
                    band, sorted(rubric)))

    # configured test commands must be proven run, with a consistent verdict.
    commands = cfg.get("testCommands") or []
    if commands:
        ran = {c.get("command"): c.get("exitCode") for c in results.get("commands") or []}
        for cmd in commands:
            if cmd not in ran:
                gaps.append("test-results.commands missing configured command: {!r}".format(cmd))
        exit_codes = [ran[c] for c in commands if c in ran]
        if exit_codes and len(exit_codes) == len(commands):
            expected = "pass" if all(x == 0 for x in exit_codes) else "fail"
            if results.get("verdict") != expected:
                gaps.append("test-results.verdict {!r} inconsistent with exit codes {} "
                            "(expected {!r})".format(results.get("verdict"), exit_codes, expected))
    return gaps


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate pack artifacts against the resolved config")
    parser.add_argument("pack_dir")
    args = parser.parse_args(argv)
    gaps = collect_gaps(args.pack_dir)
    for g in gaps:
        print("CONTRACT: " + g, file=sys.stderr)
    print("contracts: {} violation(s)".format(len(gaps)))
    return 1 if gaps else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests + full suite** — all green.

- [ ] **Step 5: Commit** — `git add scripts/validate_contracts.py tests/test_validate_contracts.py && git commit -m "feat(gates): contract validator — analysis/test-results checked against config by code"`

---

### Task 4: Wire the gates into the pipeline — evaluator schema, skill halts, render backstop

**Files:**
- Modify: `agents/eval-pack-evaluator.md`
- Modify: `skills/generate/SKILL.md` (Step 3 output shape; after Step 4)
- Modify: `scripts/render_html.py` (`validate_pack`)
- Test: `tests/test_render_contract_backstop.py` (new)

- [ ] **Step 1: Evaluator schema additions — in `agents/eval-pack-evaluator.md`:**

In the config-reading list near the top, extend the `retrospectiveQuestions` and `rubric` bullets to:

```markdown
- `retrospectiveQuestions`: if non-empty, you MUST answer every question. Emit
  `retrospectiveAnswers`: an array of `{"question": "<the question, verbatim>", "answer": "..."}`
  covering each configured question. A validator checks this mechanically; an unanswered
  question halts the pipeline.
- `rubric`: if non-empty, anchor `confidencePercent` to its bands and emit
  `rubricApplied`: `{"band": "<a key that exists in the rubric>", "why": "one sentence"}`.
  A validator rejects a band name that is not a configured rubric key.
```

And in the JSON schema block, after the `"frictionLog"` entry, add:

```json
  "retrospectiveAnswers": [
    {"question": "Configured question, verbatim", "answer": "Your answer."}
  ],
  "rubricApplied": {"band": "rubric band key", "why": "One sentence on why this band applies"},
```

Also change the `frictionLog` schema line's type description from `"one of eval-config.json frictionCategories (default: tooling|structure|naming|docs|other)"` to `"MUST be one of eval-config.json frictionCategories — a validator rejects anything else"`.

- [ ] **Step 2: Generate skill — test-results shape + validation halt.**

In `skills/generate/SKILL.md` Step 3, immediately after the existing "run EXACTLY those commands" paragraph, add:

```markdown
When `testCommands` ran, `test-results.json` MUST record the proof — one entry per configured
command, verbatim, with its real exit code — and the verdict MUST follow the exit codes
(all zero → `pass`, any nonzero → `fail`). A validator enforces this mechanically:

​```json
{
  "verdict": "fail",
  "summary": "1 of 2 configured commands failed",
  "commands": [
    {"command": "<verbatim from testCommands>", "exitCode": 0},
    {"command": "<verbatim from testCommands>", "exitCode": 1}
  ],
  "testsRun": [ {"name": "…", "passed": false, "output": "…"} ]
}
​```
```

After Step 4's existing "Confirm `${ABS_PACK_DIR}/analysis.json` exists and has a `title`" paragraph, add a new gate paragraph:

```markdown
Then run the deterministic contract gate — it checks the analysis and test results against the
resolved config (friction taxonomy, retrospective answers, rubric band, test-command proof):

​```bash
"$PYTHON" "${CLAUDE_PLUGIN_ROOT}/scripts/validate_contracts.py" "${ABS_PACK_DIR}"
​```

If it exits non-zero: re-dispatch the evaluator ONCE, passing the printed `CONTRACT:` lines as
corrections to address. If it fails again, STOP and show the user the violations — do not render.
(render_html enforces the same gate; skipping this step cannot ship a non-conforming pack.)
```

- [ ] **Step 3: Render backstop — failing test first. Create `tests/test_render_contract_backstop.py`:**

```python
# tests/test_render_contract_backstop.py
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import render_html  # noqa: E402
import config  # noqa: E402


class TestContractBackstop(unittest.TestCase):
    def test_validate_pack_includes_contract_gaps(self):
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d)
            base = dict(json.loads(json.dumps(config.DEFAULTS)))
            base["retrospectiveQuestions"] = ["Q1?"]
            (pack / "eval-config.json").write_text(json.dumps(base), encoding="utf-8")
            (pack / "transcript.jsonl").write_text(json.dumps(
                {"type": "assistant", "message": {"content": "hi"}}) + "\n", encoding="utf-8")
            (pack / "metrics.json").write_text(json.dumps({"turnCount": 1}), encoding="utf-8")
            (pack / "analysis.json").write_text(json.dumps({"title": "t"}), encoding="utf-8")
            gaps = render_html.validate_pack(pack)
            self.assertTrue(any("retrospectiveAnswers" in g for g in gaps))


if __name__ == "__main__":
    unittest.main()
```

Run: `python3 -m unittest tests.test_render_contract_backstop -v` → FAIL.

- [ ] **Step 4: Implement the backstop.** In `scripts/render_html.py`, add to the sibling imports (next to `import redact` / `from config import read_config`):

```python
import validate_contracts  # noqa: E402
```

and at the end of `validate_pack(pack_dir)`, before `return gaps`:

```python
    # Deterministic backstop: even if the orchestrating skill skipped the contract gate,
    # a non-conforming pack must not render.
    gaps.extend(validate_contracts.collect_gaps(pack_dir))
```

Run the new test → PASS; full suite → green (packs without configured questions/rubric/commands produce zero contract gaps — defaults are empty).

- [ ] **Step 5: Commit** — `git add agents/eval-pack-evaluator.md skills/generate/SKILL.md scripts/render_html.py tests/test_render_contract_backstop.py && git commit -m "feat(gates): evaluator compliance schema + skill halt + render backstop"`

---

### Task 5: Resolve-time gates — evaluatorPromptFile, rubric shape, extends-in-local, env traps (findings #8, #4-shape, #11, #10)

**Files:**
- Modify: `scripts/config.py` (`validate`, `_coerce`, `load_config`)
- Modify: `scripts/resolve_config.py` (promptFile existence)
- Test: `tests/test_config.py`, `tests/test_resolve_config.py` (append)

- [ ] **Step 1: Failing tests. Append to `tests/test_config.py`:**

```python
class TestResolveTimeGates(unittest.TestCase):
    def test_rubric_values_must_be_strings(self):
        errs = config.validate({"rubric": {"high": 42}})
        self.assertTrue(any("rubric" in e for e in errs))
        self.assertEqual(config.validate({"rubric": {"high": "no bugs"}}), [])

    def test_extends_in_local_raises(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "base.json", {"retryAmberThreshold": 2})
            _write(d, ".eval-pack.local.json", {"extends": ["base.json"]})
            with self.assertRaises(config.ConfigError) as ctx:
                config.load_config(d, env={})
            self.assertIn("local", str(ctx.exception))

    def test_env_dict_raises_clearly(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(config.ConfigError) as ctx:
                config.load_config(d, env={"CLAUDE_PLUGIN_OPTION_rubric": "high=good"})
            self.assertIn("JSON", str(ctx.exception))

    def test_env_json_array_and_object_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = config.load_config(d, env={
                "CLAUDE_PLUGIN_OPTION_redaction": '["secret{1,3}"]',
                "CLAUDE_PLUGIN_OPTION_rubric": '{"high": "ship"}',
            })
            self.assertEqual(cfg["redaction"], ["secret{1,3}"])  # comma survives (JSON, not split)
            self.assertEqual(cfg["rubric"], {"high": "ship"})
```

Append to `tests/test_resolve_config.py`:

```python
class TestPromptFileGate(unittest.TestCase):
    def test_missing_evaluator_prompt_file_halts(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as pack:
            (Path(root) / ".eval-pack.json").write_text(
                json.dumps({"evaluatorPromptFile": "nope/prompt.md"}), encoding="utf-8")
            r = _run([root, pack])
            self.assertEqual(r.returncode, 1)
            self.assertIn("evaluatorPromptFile", r.stderr)

    def test_existing_prompt_file_ok(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as pack:
            (Path(root) / "prompt.md").write_text("extra guidance", encoding="utf-8")
            (Path(root) / ".eval-pack.json").write_text(
                json.dumps({"evaluatorPromptFile": "prompt.md"}), encoding="utf-8")
            r = _run([root, pack])
            self.assertEqual(r.returncode, 0, r.stderr)
```

- [ ] **Step 2: Run to verify failures.**

- [ ] **Step 3: Implement in `scripts/config.py`:**

a) In `validate`, next to the existing rubric/dict checks (before `return errors`):

```python
    rubric = cfg.get("rubric")
    if isinstance(rubric, dict):
        for band, criteria in rubric.items():
            if not isinstance(criteria, str):
                errors.append("rubric.{}: criteria must be a string, got {}".format(
                    band, type(criteria).__name__))
```

b) In `_coerce`, replace the bare `if typ is list:` branch and add dict handling — JSON-first for both (fixes the comma-split trap on regexes AND makes dicts expressible):

```python
    if typ in (list, dict):
        raw_s = raw.strip()
        if raw_s.startswith("[") or raw_s.startswith("{"):
            try:
                val = json.loads(raw_s)
            except json.JSONDecodeError as exc:
                raise ConfigError(
                    "CLAUDE_PLUGIN_OPTION_{}: invalid JSON ({})".format(key, exc)) from exc
            if not isinstance(val, typ):
                raise ConfigError("CLAUDE_PLUGIN_OPTION_{}: expected {}, got {}".format(
                    key, typ.__name__, type(val).__name__))
            return val
        if typ is dict:
            raise ConfigError(
                "CLAUDE_PLUGIN_OPTION_{}: dict values must be JSON (e.g. '{{\"k\": \"v\"}}')".format(key))
        # legacy comma-list shorthand for simple values
        return _dedupe([s for s in raw.split(",") if s])
```

c) In `load_config`, after `local_cfg = _read_json(...)`:

```python
    if "extends" in local_cfg:
        raise ConfigError(
            "extends is not allowed in .eval-pack.local.json (project file only) — "
            "it would be silently ignored otherwise")
```

d) In `scripts/resolve_config.py`, after the stance block (before the can-never-fail warning):

```python
    prompt_file = cfg.get("evaluatorPromptFile") or ""
    if prompt_file and not (Path(args.project_root) / prompt_file).is_file():
        print("ERROR: evaluatorPromptFile {!r} not found under {}".format(
            prompt_file, args.project_root), file=sys.stderr)
        return 1
```

- [ ] **Step 4: Run tests + full suite** — green. NOTE: `test_env_list_override_replaces` (existing, uses `"a,b,c"`) must still pass — the comma shorthand is preserved for non-JSON values.

- [ ] **Step 5: Commit** — `git add scripts/config.py scripts/resolve_config.py tests/test_config.py tests/test_resolve_config.py && git commit -m "feat(gates): resolve-time checks — prompt file, rubric shape, local extends, JSON env values"`

---

### Task 6: List replace semantics — `"!replace"` sentinel (finding #5)

**Files:**
- Modify: `scripts/config.py` (`_overlay`), `schema/eval-pack.schema.json` (descriptions only — no default changes)
- Test: `tests/test_config.py` (append)

- [ ] **Step 1: Failing test — append to `tests/test_config.py`:**

```python
class TestListReplaceSentinel(unittest.TestCase):
    def test_replace_sentinel_replaces_instead_of_concat(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, ".eval-pack.json",
                   {"frictionCategories": ["!replace", "ci-flake", "review-latency"]})
            cfg = config.load_config(d, env={})
            self.assertEqual(cfg["frictionCategories"], ["ci-flake", "review-latency"])

    def test_without_sentinel_still_concats(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, ".eval-pack.json", {"frictionCategories": ["ci-flake"]})
            cfg = config.load_config(d, env={})
            self.assertEqual(cfg["frictionCategories"],
                             ["tooling", "structure", "naming", "docs", "other", "ci-flake"])
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement — in `scripts/config.py` `_overlay`, replace the list branch:**

```python
        if isinstance(v, list) and isinstance(base.get(k), list):
            if v and v[0] == "!replace":
                # explicit replace: user opts out of additive merge for this list
                base[k] = list(v[1:])
            else:
                base[k] = _dedupe(base[k] + v)
```

Update `load_config`'s docstring list-merge sentence to mention the sentinel, and in `schema/eval-pack.schema.json` append to the `frictionCategories` and `tokenFieldNames` descriptions: `" File-layer lists ADD to defaults; start the list with \"!replace\" to replace instead."`

- [ ] **Step 4: Run tests + full suite** — green (schema-sync compares types+defaults, not descriptions).

- [ ] **Step 5: Commit** — `git add scripts/config.py schema/eval-pack.schema.json tests/test_config.py && git commit -m "feat(config): !replace sentinel — file-layer lists can replace, not just add"`

---

### Task 7: Config unification — retire the split brain (finding #7)

Move `outputDir`, `analysis`, `includeTranscript`, `ticketBaseUrl` into the layered config (the `CLAUDE_PLUGIN_OPTION_*` env layer keeps old plugin-option behavior working verbatim). `pythonExecutable` stays plugin-level (bootstrap: needed before any script runs).

**Files:**
- Modify: `scripts/config.py`, `schema/eval-pack.schema.json`
- Modify: `scripts/render_html.py` (`_include_transcript`)
- Modify: `skills/generate/SKILL.md`, `skills/review/SKILL.md` (read from resolved config)
- Test: `tests/test_config.py` (append)

- [ ] **Step 1: Failing test — append to `tests/test_config.py`:**

```python
class TestUnifiedKeys(unittest.TestCase):
    def test_new_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = config.load_config(d, env={})
            self.assertEqual(cfg["outputDir"], ".eval-packs")
            self.assertIs(cfg["analysis"], True)
            self.assertIs(cfg["includeTranscript"], True)
            self.assertEqual(cfg["ticketBaseUrl"], "")

    def test_legacy_env_layer_still_wins(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = config.load_config(d, env={"CLAUDE_PLUGIN_OPTION_includeTranscript": "false"})
            self.assertIs(cfg["includeTranscript"], False)
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement:**

a) `config.py` DEFAULTS (append) + `_TYPES`:

```python
    # Pipeline options, unified from the legacy pluginConfigs home. The
    # CLAUDE_PLUGIN_OPTION_* env layer keeps old plugin-option settings working.
    "outputDir": ".eval-packs",
    "analysis": True,
    "includeTranscript": True,
    "ticketBaseUrl": "",
```

```python
    "outputDir": str,
    "analysis": bool,
    "includeTranscript": bool,
    "ticketBaseUrl": str,
```

b) Schema (append; defaults byte-match):

```json
    "outputDir": { "type": "string", "default": ".eval-packs", "description": "Directory where eval packs are written, relative to project root." },
    "analysis": { "type": "boolean", "default": true, "description": "Dispatch the AI evaluator; false emits heuristic flags only." },
    "includeTranscript": { "type": "boolean", "default": true, "description": "Bundle the raw transcript.jsonl in the pack." },
    "ticketBaseUrl": { "type": "string", "default": "", "description": "Prefix turning a bare ticket key into a link in PR bodies." },
```

c) `render_html.py`: replace `_include_transcript()`'s env read with the resolved config — find the function and change its body to accept the already-loaded `cfg`: simplest content-preserving change is to replace the call site `include_transcript = _include_transcript()` with `include_transcript = bool(cfg["includeTranscript"])` and DELETE `_include_transcript` (grep for other callers first; if tests call it, keep it delegating: `def _include_transcript(): return bool(read_config()["includeTranscript"])` — read the file and pick the minimal correct form).

d) `skills/generate/SKILL.md`: where the skill references the `analysis` plugin option ("**If analysis is enabled** (plugin config `analysis` option, default true)"), change to "(`analysis` in the resolved `eval-config.json`, default true)". Where `outputDir` is described ("outputDir from plugin config, default `.eval-packs`"), change to "(`outputDir` from the resolved `eval-config.json`, default `.eval-packs` — legacy plugin option still works via the env layer)".

e) `skills/review/SKILL.md`: the ticket-line section reads "the plugin config `ticketBaseUrl`" — change to "`ticketBaseUrl` from the resolved config (`.eval-pack.json` or legacy plugin option)".

- [ ] **Step 4: Run tests + full suite** — green. Baseline check: `python3 -c "import sys;sys.path.insert(0,'scripts');import config;c=config.read_config();assert len(c)==37 and c['outputDir']=='.eval-packs';print('37 keys OK')"`

- [ ] **Step 5: Commit** — `git add scripts/config.py schema/eval-pack.schema.json scripts/render_html.py skills/generate/SKILL.md skills/review/SKILL.md tests/test_config.py && git commit -m "feat(config): unify pipeline options into layered config (env layer keeps legacy behavior)"`

---

### Task 8: Discoverability — README rewrite, wizard enumerates the surface, offline $schema (finding #3)

**Files:**
- Modify: `README.md` (Configuration section)
- Modify: `skills/setup/SKILL.md` (Step 4 writes local schema; Step 6 enumerates surface)

- [ ] **Step 1: README.** Replace the existing configuration section (the one documenting `.claude/settings.json` → `pluginConfigs` with 4 options) with a section documenting the real system. Write it fresh (adapt the intro sentence to match surrounding tone). It MUST cover, with copy-paste examples:

```markdown
## Configuration

eval-pack is configured per-repo via `.eval-pack.json` (committed) and
`.eval-pack.local.json` (gitignored, per-developer). Layering, lowest to highest:
bundled defaults < `extends` presets < `.eval-pack.json` < `.eval-pack.local.json` <
`CLAUDE_PLUGIN_OPTION_*` env. Validation is fail-loud: an unknown key, bad type, bad
regex, or missing referenced file halts generation with a precise error. Run
`/eval-pack:setup` for a guided start.

​```json
{
  "$schema": "./.eval-pack.schema.json",
  "testCommands": ["npm test"],
  "ticketPattern": "ACME-\\d+",
  "analysisStance": "collaborative-coach",
  "rubric": {
    "ship": "All acceptance criteria demonstrated with test output",
    "hold": "Any claim of success without observed evidence"
  },
  "retrospectiveQuestions": ["What slowed the session down the most?"],
  "redaction": ["sk-[A-Za-z0-9]+"],
  "flagSeverities": {"scopeDrift": "off"},
  "costBudgetTokens": 50000000,
  "brandName": "Acme Eval", "subjectNoun": "service", "defaultTheme": "light",
  "templateDir": "eval-theme",
  "analysisLenses": [{"skill": "acme-security-lens", "role": "scorer"}],
  "verdictAggregation": "min"
}
​```

Key groups (full key list + types: `schema/eval-pack.schema.json`):
- **Evaluation prompts** — `analysisStance` (bundled: skeptical-reviewer, collaborative-coach,
  compliance-auditor; or your own at `.eval-pack/stances/<name>.md`), `rubric` (band → criteria;
  the evaluator must name the band it applied, and a validator rejects unknown bands),
  `retrospectiveQuestions` (each must be answered — validated), `evaluatorPromptFile`
  (extra grading guidance from a file in your repo).
- **Heuristics** — `detectionPatterns` (regex lists; start a list with `"!replace"` to replace
  defaults instead of adding), `falseCompletionWindow`, `scopeDriftFileThreshold`,
  `retryAmberThreshold`, `flagSeverities` (retune or `"off"` any flag by id), `costBudgetTokens`.
- **Tests & tickets** — `testCommands` (run verbatim; real exit codes drive the verdict, enforced
  by a validator), `ticketPattern`, `ticketBaseUrl`.
- **Security** — `redaction` (regexes masked in every emitted artifact, keys and values, before
  escaping), `publishOpenable`, `openableDir`.
- **Report** — `brandName`, `reportTitle`, `footerText`, `subjectNoun`, `defaultTheme`,
  `sections`, `messages`, `templateDir` (project dir overriding index.html/styles.css/scripts.js
  per-file), `zipNameTemplate`, `commitUrlTemplate`, `repoBaseUrl`.
- **Pipeline** — `outputDir`, `analysis`, `includeTranscript`.

### Extension lenses — your own analyses and scores

A lens is YOUR agent that runs during evaluation. Declare it:

​```json
{ "analysisLenses": [{ "skill": "acme-security-lens", "role": "scorer" }],
  "verdictAggregation": "min" }
​```

and provide an agent by that name (e.g. `.claude/agents/acme-security-lens.md` in your repo).
It receives PACK_DIR / REPO_ROOT / DIFF_BASE and must write
`PACK_DIR/lenses/acme-security-lens.json`:

- **scorer** (influences the verdict via `verdictAggregation`):
  `{"skill": "acme-security-lens", "role": "scorer", "score": 61, "rationale": "one sentence",
    "findings": [{"type": "issue", "detail": "..."}]}`
- **contributor** (adds an attributed report section, never touches the score):
  `{"skill": "...", "role": "contributor", "title": "Section title", "findings": ["...", "..."]}`

Guarantees, enforced by code: a configured lens that produces no output becomes a red
"Lens failed" flag (it cannot silently vanish); scorer scores are clamped to 0–100 and reach
the verdict banner and confidence card only through your declared aggregation rule; a failing
lens never crashes the eval. Bundled examples: `requirement-drift`, `verification-rigor`.
​```

(Adjust the old section's remaining valid content — `pythonExecutable` stays a plugin option in
`.claude/settings.json` because it must resolve before any script can run; keep that note.)

- [ ] **Step 2: Wizard — offline schema + surface enumeration.** In `skills/setup/SKILL.md`:

In Step 4 (Write), add a new item after the `.eval-pack.local.json` item:

```markdown
3. `.eval-pack.schema.json` (committed) — copy it from `${CLAUDE_PLUGIN_ROOT}/schema/eval-pack.schema.json`
   so the `$schema` reference resolves offline and editors validate immediately:

   ​```bash
   cp "${CLAUDE_PLUGIN_ROOT}/schema/eval-pack.schema.json" .eval-pack.schema.json
   ​```
```

(renumber the following items), and change the Step 2 example's `$schema` line to `"$schema": "./.eval-pack.schema.json"`.

In Step 6 (Report), add a bullet:

```markdown
- The full customization surface, grouped: prompts (stance/rubric/retrospectiveQuestions/
  evaluatorPromptFile), heuristics (detectionPatterns/flagSeverities/thresholds/costBudgetTokens),
  tests & tickets (testCommands/ticketPattern), security (redaction/publishOpenable), report
  (branding/templateDir/sections), and extension lenses (analysisLenses + verdictAggregation) —
  with a pointer to the README Configuration section and `.eval-pack.schema.json` for details.
```

- [ ] **Step 3: Verify by grep** — `grep -c "eval-pack.json" README.md` ≥ 3; `grep -n "pluginConfigs" README.md` mentions only `pythonExecutable`/legacy note; `grep -n "eval-pack.schema.json" skills/setup/SKILL.md` ≥ 2.

- [ ] **Step 4: Commit** — `git add README.md skills/setup/SKILL.md && git commit -m "docs: README documents the real config system; wizard ships offline schema + enumerates surface"`

---

### Task 9: Full verification + baseline + suites

- [ ] **Step 1: Baseline invariant**

```bash
python3 -c "
import sys; sys.path.insert(0, 'scripts'); import config
c = config.read_config()
assert len(c) == 37, len(c)
assert c['scopeDriftFileThreshold'] == 10 and c['skillArgsMaxLen'] == 200
assert c['outputDir'] == '.eval-packs' and c['analysis'] is True and c['includeTranscript'] is True
print('baseline OK — 37 keys, defaults preserve behavior')
"
```

- [ ] **Step 2: All suites** — `python3 -m unittest discover -s tests -p "test_*.py"` (expect ~165+, OK) and `node --test tests/lens-render.test.mjs tests/cost.test.mjs tests/lightbox-helpers.test.mjs` (expect 22+, 0 fail) and `node --check templates/html/scripts.js`.

- [ ] **Step 3: End-to-end gate proof** — a full render must REFUSE on a contract violation:

```bash
OUT=$(mktemp -d); SID=gate; PACK=$OUT/$SID; mkdir -p $PACK; REPO=$(mktemp -d)
python3 -c "import json;json.dump({'retrospectiveQuestions':['Q1?']}, open('$REPO/.eval-pack.json','w'))"
python3 scripts/resolve_config.py "$REPO" "$PACK"
python3 -c "import json;json.dump({'title':'t'}, open('$PACK/analysis.json','w'))"
python3 -c "import json;json.dump({'turnCount':2,'filesChanged':1}, open('$PACK/metrics.json','w'))"
python3 -c "import json;json.dump({'flags':[]}, open('$PACK/patterns.json','w'))"
python3 -c "import json;print(json.dumps({'type':'assistant','message':{'content':'work'}}))" > $PACK/transcript.jsonl
python3 scripts/render_html.py "$OUT" "$SID" "$(pwd)" "$PACK/transcript.jsonl" --branch gate; echo "exit=$?"
```

Expected: `exit=1` with a `retrospectiveAnswers` gap in stderr, no zip produced. Then confirm the conforming case renders (add `"retrospectiveAnswers":[{"question":"Q1?","answer":"a"}]` to analysis.json, re-run → exit 0).

- [ ] **Step 4: Commit any stragglers** — working tree must be clean.

---

### Task 10: Push, sync install, refresh PR (finding #12)

- [ ] **Step 1: Push + re-sync installed plugin**

```bash
git push
MP=~/.claude/plugins/marketplaces/eval-pack; DEST=~/.claude/plugins/cache/eval-pack/eval-pack/0.3.3
git -C $MP fetch -q origin feat/config-foundation && git -C $MP reset -q --hard FETCH_HEAD
rsync -a --delete --exclude '.git' "$MP/" "$DEST/"
python3 -c "import json;p='$HOME/.claude/plugins/installed_plugins.json';d=json.load(open(p));d['plugins']['eval-pack@eval-pack'][0]['gitCommitSha']='$(git -C $MP rev-parse HEAD)';json.dump(d,open(p,'w'),indent=2)"
```

- [ ] **Step 2: Refresh PR #13 body** — `gh pr edit 13 --body ...` with corrected numbers (37 config keys, current commit/test counts from `git rev-list --count main..HEAD` and the suite run) and a new "Deterministic gates" section: contract validator + render backstop, lens completeness gate, lens verdict integration, resolve-time gates, `!replace`, config unification, README/discoverability. Keep the existing structure and the Claude Code attribution footer.

- [ ] **Step 3: Report** — which adversarial findings are closed (#1,#2,#3,#4,#5,#6,#7,#8,#9,#10,#11,#12) and what remains instruction-level by necessity (stance tone, prose quality — now bounded by mechanical checks on their artifacts).
