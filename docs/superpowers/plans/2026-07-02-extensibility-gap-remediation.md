# Extensibility Gap Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close every gap the extensibility audit found between the promised customization surface and the shipped code — dead knobs (#5, #6), the extract_tools config clobber, the missing `templateDir` override, and the never-implemented detection/cost knobs (#12–16) — so nothing a user plausibly tunes requires a plugin-source edit.

**Architecture:** All new knobs follow the established pattern: key in `config.DEFAULTS` + `_TYPES`, mirrored in `schema/eval-pack.schema.json` (the schema-sync test enforces parity), consumed via `read_config(--config)` in scripts or via `eval-config.json` instructions in skills/agents. Baseline invariant holds: every new default reproduces today's hardcoded behavior exactly.

**Tech Stack:** Python 3 stdlib only (no pip deps; CI is `python -m unittest`, Windows-safe). Machine has `python3`, NOT `python`.

**Deferred by decision (not in this plan):** cross-repo `extends` refs — they conflict with the `extends`-confined-to-repo security guard added for path escapes; needs a design decision (trusted source registry?) before code. Documented as a known limitation.

**Working directory:** `/Users/jasonsmith/Code/eval-pack-config-foundation` (worktree, branch `feat/config-foundation`). Commit there.

---

### Task 1: Fix the extract_tools config clobber in render_html

`load_round_inputs` re-runs `extract_tools.py` WITHOUT `--config`, overwriting the config-aware `tools.json` written earlier in the pipeline — a user's `skillArgsMaxLen` silently reverts to 200 in the shipped pack.

**Files:**
- Modify: `scripts/render_html.py` (`load_round_inputs`, ~line 229; its call site in `main`, ~line 463)
- Test: `tests/test_render_config_threading.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_render_config_threading.py
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import render_html  # noqa: E402


def _skill_line(arg_len):
    return json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Skill", "id": "s1",
         "input": {"skill": "demo", "args": "x" * arg_len}}
    ]}})


class TestLoadRoundInputsThreadsConfig(unittest.TestCase):
    def test_extract_tools_rerun_honors_config(self):
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d)
            (pack / "transcript.jsonl").write_text(_skill_line(50) + "\n", encoding="utf-8")
            cfg_path = pack / "eval-config.json"
            cfg_path.write_text(json.dumps({"skillArgsMaxLen": 10}), encoding="utf-8")
            (pack / "analysis.json").write_text(json.dumps({"title": "t"}), encoding="utf-8")
            render_html.load_round_inputs(pack, pack / "transcript.jsonl", SCRIPTS)
            tools = json.loads((pack / "tools.json").read_text(encoding="utf-8"))
            self.assertEqual(len(tools["skills"][0]["args"]), 10,
                             "re-run of extract_tools must pass --config, not clobber with defaults")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_render_config_threading -v`
Expected: FAIL — args length is 50 truncated to 200-default (i.e. 50), not 10.

- [ ] **Step 3: Fix `load_round_inputs`**

In `scripts/render_html.py`, change the `extract_tools` invocation inside `load_round_inputs` from:

```python
        ok = run_script(scripts_dir / "extract_tools.py", [transcript_file, pack_dir])
```

to:

```python
        tools_args = [transcript_file, pack_dir]
        cfg_file = Path(pack_dir) / "eval-config.json"
        if cfg_file.is_file():
            tools_args += ["--config", cfg_file]
        ok = run_script(scripts_dir / "extract_tools.py", tools_args)
```

No signature change needed — the config lives in the pack dir it already receives.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_render_config_threading -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/render_html.py tests/test_render_config_threading.py
git commit -m "fix(render): thread --config into extract_tools re-run (skillArgsMaxLen clobber)"
```

---

### Task 2: Add the 8 missing config keys (+ validation + schema)

Keys: `templateDir`, `detectionPatterns`, `falseCompletionWindow`, `claimTruncLen`, `flagSeverities`, `tokenFieldNames`, `tokenWeights`, `costBudgetTokens`. Defaults reproduce today's hardcoded behavior.

**Files:**
- Modify: `scripts/config.py` (DEFAULTS, `_TYPES`, `validate`)
- Modify: `schema/eval-pack.schema.json`
- Test: `tests/test_config.py` (append)

- [ ] **Step 1: Write the failing tests — append to `tests/test_config.py` before `if __name__`:**

```python
class TestDetectionCostKeys(unittest.TestCase):
    def test_new_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = config.load_config(d, env={})
            self.assertEqual(cfg["templateDir"], "")
            self.assertEqual(cfg["falseCompletionWindow"], 1)
            self.assertEqual(cfg["claimTruncLen"], 120)
            self.assertEqual(cfg["flagSeverities"], {})
            self.assertEqual(cfg["tokenFieldNames"], ["subagent_tokens", "total_tokens"])
            self.assertEqual(cfg["tokenWeights"], {})
            self.assertEqual(cfg["costBudgetTokens"], 0)
            self.assertIn("done", cfg["detectionPatterns"])
            self.assertIn("correction", cfg["detectionPatterns"])
            self.assertIn("retry", cfg["detectionPatterns"])

    def test_detection_pattern_bad_regex_rejected(self):
        errs = config.validate({"detectionPatterns": {"done": ["("]}})
        self.assertTrue(any("detectionPatterns" in e for e in errs))

    def test_flag_severity_enum(self):
        self.assertEqual(config.validate({"flagSeverities": {"highRetry": "red"}}), [])
        errs = config.validate({"flagSeverities": {"highRetry": "purple"}})
        self.assertTrue(any("flagSeverities" in e for e in errs))

    def test_token_weights_numeric(self):
        self.assertEqual(config.validate({"tokenWeights": {"input": 2}}), [])
        errs = config.validate({"tokenWeights": {"input": "two"}})
        self.assertTrue(any("tokenWeights" in e for e in errs))
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m unittest tests.test_config -v` — expect FAILs (unknown keys).

- [ ] **Step 3: Edit `scripts/config.py`**

a) Append to `DEFAULTS` (after `messages`):

```python
    # Project-relative dir holding report template overrides (index.html/styles.css/scripts.js);
    # empty means the bundled templates.
    "templateDir": "",
    # Heuristic detection regexes (lists are OR-combined). Defaults are today's English patterns.
    "detectionPatterns": {
        "done": [r"(?i)(done|complete|finished|all set|that should|looks good now)"],
        "correction": [r"(?i)(no|not|wrong|still|actually|but|fix|fail|error|broken|issue)"],
        "retry": [r"(?i)(try again|retry|let me try|another approach|different approach)"],
    },
    # How many following entries to scan for a user correction after a completion claim.
    "falseCompletionWindow": 1,
    # Truncation length for quoted claim/response text in patterns.json.
    "claimTruncLen": 120,
    # Per-flag severity overrides: {flagId: "red"|"amber"|"green"|"off"}. Empty = built-in levels.
    "flagSeverities": {},
    # Field names accepted when parsing subagent token usage from Agent tool results.
    "tokenFieldNames": ["subagent_tokens", "total_tokens"],
    # Optional weights for the total-token sum: {"input","output","cacheRead","cacheWrite"}.
    # Empty = plain unweighted sum (today's behavior).
    "tokenWeights": {},
    # Amber-flag the session when totalTokens exceeds this budget; 0 disables.
    "costBudgetTokens": 0,
```

b) Append to `_TYPES`:

```python
    "templateDir": str,
    "detectionPatterns": dict,
    "falseCompletionWindow": int,
    "claimTruncLen": int,
    "flagSeverities": dict,
    "tokenFieldNames": list,
    "tokenWeights": dict,
    "costBudgetTokens": int,
```

c) Add a severity constant near `THEMES`:

```python
# Allowed per-flag severity overrides.
FLAG_LEVELS = ("red", "amber", "green", "off")
```

d) In `validate(cfg)`, just before `return errors`, add:

```python
    dp = cfg.get("detectionPatterns")
    if isinstance(dp, dict):
        for group, pats in dp.items():
            if not isinstance(pats, list):
                errors.append("detectionPatterns.{}: expected list of regexes".format(group))
                continue
            for pat in pats:
                try:
                    re.compile(pat)
                except re.error as exc:
                    errors.append("detectionPatterns.{}: invalid regex {!r} ({})".format(group, pat, exc))
    sevs = cfg.get("flagSeverities")
    if isinstance(sevs, dict):
        for fid, level in sevs.items():
            if level not in FLAG_LEVELS:
                errors.append("flagSeverities.{}: {!r} is not one of {}".format(fid, level, list(FLAG_LEVELS)))
    weights = cfg.get("tokenWeights")
    if isinstance(weights, dict):
        for k, v in weights.items():
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                errors.append("tokenWeights.{}: expected a number, got {}".format(k, type(v).__name__))
```

- [ ] **Step 4: Edit `schema/eval-pack.schema.json`** — add after `messages` (defaults must byte-match DEFAULTS; the schema-sync test compares them):

```json
    "templateDir": { "type": "string", "default": "", "description": "Project-relative dir with report template overrides; empty uses bundled." },
    "detectionPatterns": {
      "type": "object",
      "default": {
        "done": ["(?i)(done|complete|finished|all set|that should|looks good now)"],
        "correction": ["(?i)(no|not|wrong|still|actually|but|fix|fail|error|broken|issue)"],
        "retry": ["(?i)(try again|retry|let me try|another approach|different approach)"]
      },
      "description": "Heuristic detection regexes (lists OR-combined)."
    },
    "falseCompletionWindow": { "type": "integer", "default": 1, "description": "Entries scanned for a user correction after a completion claim." },
    "claimTruncLen": { "type": "integer", "default": 120, "description": "Truncation length for quoted claims in patterns.json." },
    "flagSeverities": { "type": "object", "default": {}, "description": "Per-flag severity overrides: {flagId: red|amber|green|off}." },
    "tokenFieldNames": { "type": "array", "items": { "type": "string" }, "default": ["subagent_tokens", "total_tokens"], "description": "Accepted subagent token field names." },
    "tokenWeights": { "type": "object", "default": {}, "description": "Optional weights for the total-token sum; empty = plain sum." },
    "costBudgetTokens": { "type": "integer", "default": 0, "description": "Amber-flag when totalTokens exceeds this; 0 disables." },
```

- [ ] **Step 5: Run the full suite**

Run: `python3 -m unittest discover -s tests -p "test_*.py"` — ALL pass, including `tests.test_schema_sync` (proves schema/DEFAULTS parity for the new keys).

- [ ] **Step 6: Commit**

```bash
git add scripts/config.py schema/eval-pack.schema.json tests/test_config.py
git commit -m "feat(config): detection/cost/template knobs (#12-16 + templateDir) with validation"
```

---

### Task 3: Configurable detection in detect_patterns (knobs #13, #14)

**Files:**
- Modify: `scripts/detect_patterns.py` (module constants `DONE_RE/CORRECTION_RE/RETRY_RE` ~line 51; `detect_false_completions` ~line 57; `detect_retries` ~line 72; `main`)
- Test: `tests/test_detect_patterns_config.py` (append)

- [ ] **Step 1: Write the failing tests — append to `tests/test_detect_patterns_config.py` before `if __name__`:**

```python
def _entry(etype, text):
    return {"type": etype, "message": {"content": [{"type": "text", "text": text}]}}


class TestConfigurableDetection(unittest.TestCase):
    def test_custom_done_pattern(self):
        entries = [_entry("assistant", "task fertig jetzt"), _entry("user", "nein, broken")]
        rx = detect_patterns.compile_patterns({"done": [r"(?i)fertig"],
                                               "correction": [r"(?i)(nein|broken)"],
                                               "retry": [r"(?i)nochmal"]})
        found = detect_patterns.detect_false_completions(entries, rx, window=1, trunc=120)
        self.assertEqual(len(found), 1)

    def test_window_extends_reach(self):
        entries = [_entry("assistant", "all done"),
                   _entry("assistant", "wrapping up"),
                   _entry("user", "no, still broken")]
        rx = detect_patterns.compile_patterns(detect_patterns.DEFAULT_PATTERNS)
        self.assertEqual(len(detect_patterns.detect_false_completions(entries, rx, window=1, trunc=120)), 0)
        self.assertEqual(len(detect_patterns.detect_false_completions(entries, rx, window=2, trunc=120)), 1)

    def test_trunc_len_applied(self):
        entries = [_entry("assistant", "done " + "x" * 300), _entry("user", "no, wrong")]
        rx = detect_patterns.compile_patterns(detect_patterns.DEFAULT_PATTERNS)
        found = detect_patterns.detect_false_completions(entries, rx, window=1, trunc=10)
        self.assertEqual(len(found[0]["agentClaim"]), 10)
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m unittest tests.test_detect_patterns_config -v` — FAIL (`compile_patterns` undefined; signature mismatch).

- [ ] **Step 3: Edit `scripts/detect_patterns.py`**

Replace the three module-level regex constants with:

```python
# Defaults mirror config.DEFAULTS["detectionPatterns"]; kept here so the module works standalone.
DEFAULT_PATTERNS = {
    "done": [r"(?i)(done|complete|finished|all set|that should|looks good now)"],
    "correction": [r"(?i)(no|not|wrong|still|actually|but|fix|fail|error|broken|issue)"],
    "retry": [r"(?i)(try again|retry|let me try|another approach|different approach)"],
}


def compile_patterns(patterns):
    """OR-combine each group's regex list into one compiled pattern per group."""
    return {
        group: re.compile("|".join("(?:{})".format(p) for p in pats))
        for group, pats in patterns.items()
    }
```

Replace `detect_false_completions` with:

```python
def detect_false_completions(entries, rx, window, trunc):
    result = []
    for i in range(len(entries) - 1):
        if entries[i].get("type") != "assistant":
            continue
        agent_text = entry_text(entries[i])
        if not rx["done"].search(agent_text):
            continue
        for j in range(i + 1, min(i + 1 + window, len(entries))):
            if not is_human(entries[j]):
                continue
            user_text = entry_text(entries[j])
            if rx["correction"].search(user_text):
                result.append({
                    "turn": i,
                    "agentClaim": agent_text[:trunc],
                    "userResponse": user_text[:trunc],
                })
            break  # judge only the first human reply in the window
    return result
```

Change `detect_retries` to take the compiled pattern — from its current use of `RETRY_RE` to:

```python
def detect_retries(entries, retry_re):
    return sum(
        1 for e in entries
        if is_human(e) and retry_re.search(entry_text(e))
    )
```

(Match the existing body shape — only the pattern source changes; read the current function first and keep its exact iteration logic, swapping `RETRY_RE` for the `retry_re` parameter.)

In `main()`, after `cfg = read_config(args.config)` add:

```python
    rx = compile_patterns(cfg.get("detectionPatterns") or DEFAULT_PATTERNS)
```

and update the call sites:

```python
    false_completions = detect_false_completions(
        entries, rx, cfg["falseCompletionWindow"], cfg["claimTruncLen"]
    )
    retry_count = detect_retries(entries, rx["retry"])
```

- [ ] **Step 4: Run tests**

Run: `python3 -m unittest tests.test_detect_patterns_config -v` then the full suite. Expected: PASS everywhere (defaults reproduce the old constants exactly — window=1 + first-human-reply matches the old adjacent-entry logic).

- [ ] **Step 5: Commit**

```bash
git add scripts/detect_patterns.py tests/test_detect_patterns_config.py
git commit -m "feat(patterns): configurable detection regexes, window, truncation (#13, #14)"
```

---

### Task 4: flagSeverities, unknown-verdict surfacing, cost budget, can-never-fail warning (knobs #12, #16-budget)

**Files:**
- Modify: `scripts/detect_patterns.py` (flags block in `main`, ~line 173)
- Modify: `scripts/resolve_config.py` (warning after validation)
- Test: `tests/test_detect_patterns_config.py`, `tests/test_resolve_config.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_detect_patterns_config.py`:

```python
class TestFlagSeverities(unittest.TestCase):
    def _run(self, cfg_extra, metrics=None, verdict=None):
        import subprocess
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d)
            (pack / "transcript.jsonl").write_text(
                json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "hi"}]}}) + "\n",
                encoding="utf-8")
            base = dict(json.loads(json.dumps(__import__("config").DEFAULTS)))
            base.update(cfg_extra)
            (pack / "eval-config.json").write_text(json.dumps(base), encoding="utf-8")
            if metrics:
                (pack / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
            if verdict:
                (pack / "test-results.json").write_text(json.dumps({"verdict": verdict}), encoding="utf-8")
            subprocess.run(
                [sys.executable, str(SCRIPTS / "detect_patterns.py"),
                 str(pack / "transcript.jsonl"), str(pack), "--config", str(pack / "eval-config.json")],
                check=True, capture_output=True, text=True)
            return json.loads((pack / "patterns.json").read_text(encoding="utf-8"))

    def test_severity_override_and_off(self):
        out = self._run({"flagSeverities": {"testsFailing": "amber"}}, verdict="fail")
        flag = next(f for f in out["flags"] if f["id"] == "testsFailing")
        self.assertEqual(flag["level"], "amber")
        out2 = self._run({"flagSeverities": {"testsFailing": "off"}}, verdict="fail")
        self.assertFalse(any(f["id"] == "testsFailing" for f in out2["flags"]))

    def test_unknown_verdict_surfaces(self):
        out = self._run({}, verdict="banana")
        self.assertTrue(any(f["id"] == "unknownVerdict" and f["level"] == "amber" for f in out["flags"]))

    def test_cost_budget_flag(self):
        out = self._run({"costBudgetTokens": 100}, metrics={"totalTokens": 500, "filesChanged": 0})
        self.assertTrue(any(f["id"] == "overBudget" for f in out["flags"]))
```

Append to `tests/test_resolve_config.py`:

```python
class TestCanNeverFailWarning(unittest.TestCase):
    def test_all_flags_disabled_warns(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as pack:
            (Path(root) / ".eval-pack.json").write_text(json.dumps({
                "flagSeverities": {k: "off" for k in
                    ["testsFailing", "testsPassing", "falseCompletions", "highRetry",
                     "scopeDrift", "partialSession", "unknownVerdict", "overBudget"]}
            }), encoding="utf-8")
            r = _run([root, pack])
            self.assertEqual(r.returncode, 0)          # warn, don't block
            self.assertIn("can never fail", r.stderr)   # but say so loudly
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m unittest tests.test_detect_patterns_config tests.test_resolve_config -v` — FAILs (`id` field absent, no unknownVerdict/overBudget, no warning).

- [ ] **Step 3: Rewrite the flags block in `detect_patterns.py:main`**

Replace the current `flags = []` block through `flags.append({"level": "green", "label": "Clean first-pass implementation"})` with:

```python
    # Built-in flags carry a stable id so users can retune severity per-flag.
    sev = cfg.get("flagSeverities") or {}

    def add_flag(fid, default_level, label, **extra):
        level = sev.get(fid, default_level)
        if level == "off":
            return
        flags.append(dict({"id": fid, "level": level, "label": label}, **extra))

    flags = []
    if test_verdict == "fail":
        add_flag("testsFailing", "red", "Tests failing at completion")
    elif test_verdict == "pass":
        add_flag("testsPassing", "green", "Tests passing at completion")
    elif test_verdict not in ("", None, "none"):
        # An unrecognized verdict must be visible, not silently identical to a clean run.
        add_flag("unknownVerdict", "amber", f"Unknown test verdict: {test_verdict!r}")
    if false_completions:
        add_flag("falseCompletions", "amber", "False completions", count=len(false_completions))
    if retry_count >= cfg["retryAmberThreshold"]:
        add_flag("highRetry", "amber", "High retry count", count=retry_count)
    if scope_drift:
        add_flag("scopeDrift", "amber", "Scope drift — many files changed")
    if partial_session:
        add_flag("partialSession", "amber", "Partial session — earlier turns may be missing")
    budget = cfg.get("costBudgetTokens") or 0
    if budget > 0:
        metrics = read_json_safe(output_dir / "metrics.json")
        total = (metrics or {}).get("totalTokens") or 0
        if total > budget:
            add_flag("overBudget", "amber", f"Over token budget ({total} > {budget})")
    if not flags:
        flags.append({"id": "cleanPass", "level": "green", "label": "Clean first-pass implementation"})
```

Add this small helper near `check_scope_drift` (reuse its defensive read style):

```python
def read_json_safe(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
```

- [ ] **Step 4: Add the can-never-fail warning to `resolve_config.py`**

After the stance-embedding block and before `if args.check:` insert:

```python
    # Sensor: a verdict config where every flag is disabled can never fail — warn, don't block.
    sev = cfg.get("flagSeverities") or {}
    if sev and all(level == "off" for level in sev.values()) and len(sev) >= 8:
        print(
            "WARNING: flagSeverities disables every built-in flag — this verdict config "
            "can never fail. Intended?",
            file=sys.stderr,
        )
```

- [ ] **Step 5: Run tests, then the full suite**

Run: `python3 -m unittest tests.test_detect_patterns_config tests.test_resolve_config -v`, then `python3 -m unittest discover -s tests -p "test_*.py"`. Expected: PASS. (Pre-existing tests asserting flag labels still pass — labels unchanged; the additive `id` field doesn't break them.)

- [ ] **Step 6: Commit**

```bash
git add scripts/detect_patterns.py scripts/resolve_config.py tests/test_detect_patterns_config.py tests/test_resolve_config.py
git commit -m "feat(patterns): flagSeverities/off, unknown-verdict + budget flags, can-never-fail warning (#12, #16)"
```

---

### Task 5: tokenFieldNames + tokenWeights in extract_metrics (knobs #15, #16-weights)

**Files:**
- Modify: `scripts/extract_metrics.py` (imports; argparse ~line 88; token regex ~line 71; total sum ~line 133)
- Modify: `skills/generate/SKILL.md` (Step 1 metrics invocation — add `--config`)
- Test: `tests/test_extract_metrics_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_extract_metrics_config.py
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _transcript(path):
    lines = [
        {"type": "assistant", "message": {"model": "m1", "usage": {
            "input_tokens": 10, "output_tokens": 20,
            "cache_read_input_tokens": 30, "cache_creation_input_tokens": 40},
            "content": [{"type": "text", "text": "hi"}]}},
    ]
    path.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")


def _run(tpath, pack, cfg_path=None):
    args = [sys.executable, str(SCRIPTS / "extract_metrics.py"), str(tpath), str(pack)]
    if cfg_path:
        args += ["--config", str(cfg_path)]
    subprocess.run(args, check=True, capture_output=True, text=True)
    return json.loads((Path(pack) / "metrics.json").read_text(encoding="utf-8"))


class TestTokenWeights(unittest.TestCase):
    def test_default_plain_sum(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as pack:
            t = Path(d) / "t.jsonl"
            _transcript(t)
            m = _run(t, pack)
            self.assertEqual(m["totalTokens"], 100)  # 10+20+30+40 — baseline preserved

    def test_weighted_sum(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as pack:
            t = Path(d) / "t.jsonl"
            _transcript(t)
            cfg = Path(d) / "eval-config.json"
            cfg.write_text(json.dumps({"tokenWeights": {"cacheRead": 0, "cacheWrite": 0}}), encoding="utf-8")
            m = _run(t, pack, cfg)
            self.assertEqual(m["totalTokens"], 30)  # 10*1 + 20*1 + 30*0 + 40*0


class TestTokenFieldNames(unittest.TestCase):
    def test_custom_field_name(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as pack:
            t = Path(d) / "t.jsonl"
            lines = [
                {"type": "assistant", "message": {"model": "m1", "content": [
                    {"type": "tool_use", "name": "Agent", "id": "a1", "input": {"model": "m2"}}],
                    "usage": {}}},
                {"type": "user", "message": {"content": [
                    {"type": "tool_result", "tool_use_id": "a1", "content": "my_tokens: 77"}]}},
            ]
            t.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
            cfg = Path(d) / "eval-config.json"
            cfg.write_text(json.dumps({"tokenFieldNames": ["my_tokens"]}), encoding="utf-8")
            m = _run(t, pack, cfg)
            self.assertEqual(m.get("subagentTotalTokens", 0), 77)


if __name__ == "__main__":
    unittest.main()
```

NOTE for the implementer: before finalizing this test, READ `scripts/extract_metrics.py` to confirm the exact transcript shape it expects for Agent tool results and the exact output key for subagent totals (`subagentTotalTokens` or similar in metrics.json) — adjust the test fixture keys to the real shapes so the test exercises the actual parser, then keep the assertion meaningful.

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m unittest tests.test_extract_metrics_config -v` — FAIL (`--config` unrecognized).

- [ ] **Step 3: Edit `scripts/extract_metrics.py`**

a) Add the sibling import after the existing imports (mirror detect_patterns.py):

```python
sys.path.insert(0, str(Path(__file__).parent))  # noqa: E402
from config import read_config  # noqa: E402
```

b) Add the argparse option next to the existing ones:

```python
    parser.add_argument("--config", default=None, help="Path to resolved eval-config.json")
```

and after `args = parser.parse_args()`:

```python
    cfg = read_config(args.config)
```

c) Replace the hardcoded token-field regex (line ~71):

```python
                m = re.search(r"(?:subagent_tokens|total_tokens):\s*(\d+)", str(inner))
```

with a pattern built once from config (hoist above the loop that uses it):

```python
    token_field_re = re.compile(
        r"(?:{}):\s*(\d+)".format("|".join(re.escape(n) for n in cfg["tokenFieldNames"]))
    )
```

and use `token_field_re.search(str(inner))` at the call site. (The function containing the loop may need `cfg` or the compiled regex passed in — thread it as a parameter, matching how the function is called from `main`.)

d) Replace the total (line ~133):

```python
    total_tokens = input_tokens + output_tokens + cache_read_tokens + cache_write_tokens
```

with:

```python
    w = cfg.get("tokenWeights") or {}
    total_tokens = (
        input_tokens * w.get("input", 1)
        + output_tokens * w.get("output", 1)
        + cache_read_tokens * w.get("cacheRead", 1)
        + cache_write_tokens * w.get("cacheWrite", 1)
    )
```

- [ ] **Step 4: Wire `--config` into the generate skill's metrics step**

In `skills/generate/SKILL.md`, find the Step 1 `extract_metrics.py` invocation and append `--config "${PACK_DIR}/eval-config.json"` to it (same pattern as the detect_patterns/extract_tools lines).

- [ ] **Step 5: Run tests + full suite**

Run: `python3 -m unittest tests.test_extract_metrics_config -v` then the full suite. Expected: PASS; pre-existing `tests.test_extract_metrics` stays green (defaults preserve the plain sum and old field names).

- [ ] **Step 6: Commit**

```bash
git add scripts/extract_metrics.py skills/generate/SKILL.md tests/test_extract_metrics_config.py
git commit -m "feat(metrics): tokenFieldNames + tokenWeights via --config (#15, #16)"
```

---

### Task 6: templateDir — project-first report template override

**Files:**
- Modify: `scripts/render_html.py` (`build_directory_structure` ~line 219; `main` template_dir resolution ~line 461)
- Test: `tests/test_template_dir.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_template_dir.py
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import render_html  # noqa: E402

BUNDLED = SCRIPTS.parent / "templates" / "html"


class TestTemplateOverride(unittest.TestCase):
    def test_user_file_wins_bundled_fills_gaps(self):
        with tempfile.TemporaryDirectory() as d:
            user_dir = Path(d) / "mytpl"
            user_dir.mkdir()
            (user_dir / "styles.css").write_text("/* CUSTOM */", encoding="utf-8")
            pack = Path(d) / "pack"
            render_html.build_directory_structure(pack, BUNDLED, user_dir)
            self.assertEqual((pack / "styles.css").read_text(encoding="utf-8"), "/* CUSTOM */")
            self.assertIn("<html", (pack / "index.html").read_text(encoding="utf-8"))  # bundled fallback

    def test_no_override_uses_bundled(self):
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d) / "pack"
            render_html.build_directory_structure(pack, BUNDLED, None)
            self.assertIn("<html", (pack / "index.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m unittest tests.test_template_dir -v` — FAIL (`build_directory_structure` takes 2 args).

- [ ] **Step 3: Implement**

Replace `build_directory_structure` in `scripts/render_html.py`:

```python
def build_directory_structure(pack_dir, template_dir, user_template_dir=None):
    """Create pack layout; copy templates project-first (user file wins, bundled fills gaps)."""
    pack_dir.mkdir(parents=True, exist_ok=True)
    (pack_dir / "screenshots").mkdir(exist_ok=True)
    (pack_dir / "logs").mkdir(exist_ok=True)
    for name in ("index.html", "styles.css", "scripts.js"):
        src = template_dir / name
        if user_template_dir is not None and (Path(user_template_dir) / name).is_file():
            src = Path(user_template_dir) / name
        shutil.copy(src, pack_dir / name)
```

In `main()`, after `redaction_rules = cfg["redaction"]`, resolve the override (project root = cwd, same convention as the openableDir guard):

```python
    user_template_dir = None
    if cfg["templateDir"]:
        user_template_dir = Path.cwd() / cfg["templateDir"]
        if not user_template_dir.is_dir():
            # Fail loud: a configured override that doesn't exist must not silently use bundled.
            print(f"Error: templateDir {user_template_dir} does not exist", file=sys.stderr)
            sys.exit(1)
```

and change the call:

```python
    build_directory_structure(pack_dir, template_dir, user_template_dir)
```

- [ ] **Step 4: Run tests + full suite**

Run: `python3 -m unittest tests.test_template_dir -v` then full suite. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/render_html.py tests/test_template_dir.py
git commit -m "feat(render): templateDir — project-first report template override"
```

---

### Task 7: Wire the two dead knobs — testCommands (generate) + ticketPattern (review)

Prose-consumer edits; verified by grep + `--check` still passing. No Python changes.

**Files:**
- Modify: `skills/generate/SKILL.md` (Step 3 "Run Tests", ~line 133)
- Modify: `skills/review/SKILL.md` (ticket-discovery block, ~lines 44–63)

- [ ] **Step 1: Rewire generate Step 3**

In `skills/generate/SKILL.md`, at the TOP of Step 3 (before the current numbered list), insert:

```markdown
First read `testCommands` from `${PACK_DIR}/eval-config.json`. **If it is non-empty, run EXACTLY
those commands** (in order, from the repo root), capture each command's real exit code and output,
and base the test verdict on those real exit codes — do not guess at runners. Only when
`testCommands` is empty fall back to the detection heuristics below:
```

- [ ] **Step 2: Rewire review ticket discovery**

In `skills/review/SKILL.md`, before the branch-name step, insert:

```markdown
Resolve the ticket pattern from config first — repos configure their own key shape via
`ticketPattern` in `.eval-pack.json`:

​```bash
TICKET_PATTERN=$("$PYTHON" -c "
import sys; sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}/scripts')
from config import load_config
print(load_config('$(pwd)')['ticketPattern'])
" 2>/dev/null || echo '[A-Z][A-Z0-9]+-[0-9]+')
​```
```

Then replace both hardcoded `grep -oE '[A-Z][A-Z0-9]+-[0-9]+'` occurrences with `grep -oE "$TICKET_PATTERN"`, and change the prose "match the default ticket pattern `[A-Z][A-Z0-9]+-[0-9]+`" to "match `$TICKET_PATTERN`".

- [ ] **Step 3: Verify by grep**

Run: `grep -n "testCommands" skills/generate/SKILL.md` — expect a hit inside Step 3.
Run: `grep -c "TICKET_PATTERN" skills/review/SKILL.md` — expect ≥3; `grep -c "grep -oE '\[A-Z\]" skills/review/SKILL.md` — expect 0.

- [ ] **Step 4: Commit**

```bash
git add skills/generate/SKILL.md skills/review/SKILL.md
git commit -m "fix(skills): consume testCommands + ticketPattern — no more dead knobs (#5, #6)"
```

---

### Task 8: Baseline invariant + full verification + push + install sync

**Files:** none new — verification only.

- [ ] **Step 1: Baseline invariant**

Run:
```bash
python3 -c "
import sys; sys.path.insert(0, 'scripts'); import config
c = config.read_config()
assert c['scopeDriftFileThreshold'] == 10 and c['retryAmberThreshold'] == 4 and c['skillArgsMaxLen'] == 200
assert c['falseCompletionWindow'] == 1 and c['claimTruncLen'] == 120 and c['costBudgetTokens'] == 0
assert c['tokenWeights'] == {} and c['flagSeverities'] == {} and c['templateDir'] == ''
print('baseline OK —', len(c), 'keys, all new defaults are no-ops')
"
```
Expected: `baseline OK — 33 keys, ...`

- [ ] **Step 2: Full suites**

Run: `python3 -m unittest discover -s tests -p "test_*.py"` — ALL pass.
Run: `node --check templates/html/scripts.js && node --test tests/cost.test.mjs tests/lightbox-helpers.test.mjs` — 19 pass.

- [ ] **Step 3: Push and re-sync the installed plugin**

```bash
git push
MP=~/.claude/plugins/marketplaces/eval-pack; DEST=~/.claude/plugins/cache/eval-pack/eval-pack/0.3.3
git -C $MP fetch -q origin feat/config-foundation && git -C $MP reset -q --hard FETCH_HEAD
rsync -a --delete --exclude '.git' "$MP/" "$DEST/"
python3 -c "import json;p='$HOME/.claude/plugins/installed_plugins.json';d=json.load(open(p));d['plugins']['eval-pack@eval-pack'][0]['gitCommitSha']='$(git -C $MP rev-parse HEAD)';json.dump(d,open(p,'w'),indent=2)"
```

- [ ] **Step 4: Report** — summarize which audit gaps are now closed and which remain deferred: cross-repo `extends` (design decision), rubric `riskLevels` vocabulary (rubric stays free-form), transcript.html theme unification, and `zipNameTemplate` `{title}` token (P2 polish).
