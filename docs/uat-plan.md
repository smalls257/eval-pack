Grounding confirmed: `merge_sessions.py` exists; the openable copy is printed by generate as `Open: file://<dir>/index.html` (dir = `<open_base>/eval-pack-<session_id>`), the zip as `Eval pack rendered to <zip>`; the old single `includeTranscript` flag is now two schema keys, `includeRawTranscript` (default `false`) and `includeRenderedTranscript` (default `true`), each settable in `.eval-pack.json` and, for standalone renders without a resolved config, as a `CLAUDE_PLUGIN_OPTION_<key>` env flag. Below is the final plan.

---

# Eval-Pack User-Customization — User Acceptance Test Plan

**Feature branch:** `feat/config-foundation`
**Central invariant:** *No config present ⇒ output is byte-for-byte today's behavior.* Everything below either proves that invariant or proves that a config knob does exactly and only what it advertises.

**Tester profile:** non-author, comfortable with a shell, `git`, `python3`, a browser, and Claude Code slash commands. No knowledge of the implementation is assumed.

---

## 0. Prerequisites & Environment

### 0.1 Check out the feature branch

```bash
cd ~/Code/eval-pack          # the plugin repo
git fetch origin
git checkout feat/config-foundation
git log --oneline -1          # note the SHA you are testing
```

### 0.2 Toolchain

```bash
python3 --version             # expect 3.8+
node --version                # expect 18+ (needed for the Lenses/template checks)
which python3 python          # record BOTH; SC-ENV-01/02 depend on knowing what's on PATH
```

### 0.3 Run the automated suite first (smoke gate)

The plan below is *acceptance* on top of unit tests. Confirm the unit floor is green before spending human time:

```bash
cd ~/Code/eval-pack
python3 -m pytest tests/test_config.py tests/test_resolve_config.py \
  tests/test_schema_sync.py tests/test_aggregate.py tests/test_redact.py \
  tests/test_detect_patterns_config.py tests/test_extract_tools_config.py -q
node --test tests/*.test.mjs 2>/dev/null || node tests/cost.test.mjs
```

**Known CI blind spot (record, do not skip):** the smoke gate above runs **no JS test over `templates/html/scripts.js`**. CI can be fully green while the rendered Lenses tab is broken (see SC-LEN-01). Treat the browser-driven template scenarios (Section 7, Section 8) as *not* covered by the unit floor.

If any unit test fails, **stop** and report — do not proceed to acceptance.

### 0.4 Key paths & primitives you will use constantly

| Thing | Value |
|---|---|
| Project config file | `<repo>/.eval-pack.json` |
| Local (gitignored) override | `<repo>/.eval-pack.local.json` |
| Env override prefix | `CLAUDE_PLUGIN_OPTION_<key>` |
| Resolver CLI (write) | `python3 scripts/resolve_config.py <project_root> <pack_dir>` |
| Resolver CLI (validate only) | `python3 scripts/resolve_config.py <project_root> --check` |
| Resolved artifact | `<pack_dir>/eval-config.json` |
| Stance presets | `presets/stances/{skeptical-reviewer,collaborative-coach,compliance-auditor}.md` |
| Aggregation rules | `core`, `min`, `mean` |
| Themes | `dark`, `light`, `system` |

**Resolver harness** (used by most config scenarios — no full generate needed):

```bash
# from the repo you are testing against:
mkdir -p /tmp/uat-pack
python3 ~/Code/eval-pack/scripts/resolve_config.py "$(pwd)" /tmp/uat-pack ; echo "exit=$?"
cat /tmp/uat-pack/eval-config.json 2>/dev/null || echo "(no eval-config.json written)"
```

### 0.5 Clean-slate reset (RUN BETWEEN EVERY SCENARIO)

Config layers and env vars leak across scenarios and will silently mask or alter an expected result. Before **each** scenario below, run this reset in the working repo, without exception:

```bash
uat_reset() {
  rm -f .eval-pack.json .eval-pack.local.json /tmp/uat-pack/eval-config.json \
        team-preset.json base-preset.json mid-preset.json 2>/dev/null
  # clear ALL plugin option env vars from the current shell:
  for v in $(env | grep -o '^CLAUDE_PLUGIN_OPTION_[A-Za-z0-9_]*' ); do unset "$v"; done
  env | grep CLAUDE_PLUGIN_OPTION && echo "!! env not clean" || echo "reset OK"
}
uat_reset
```

Any scenario that sets an env var must set it **inline** on the command (`VAR=x python3 …`) or explicitly `unset` it at the end; never leave one exported.

### 0.6 A sample target repo with a transcript

`/eval-pack:generate` reads the **current Claude Code session transcript**. To exercise a full run:

1. Create a throwaway repo: `mkdir /tmp/uat-target && cd /tmp/uat-target && git init && echo "# demo" > README.md && git add -A && git commit -m "seed"`.
2. Open a Claude Code session in `/tmp/uat-target` with the eval-pack plugin loaded on `feat/config-foundation`.
3. Have a short throwaway conversation (a few turns of real work) so there is a transcript to evaluate.
4. Run `/eval-pack:setup` then `/eval-pack:generate`.

For config/security/lens scenarios that don't need a fresh conversation, prefer the **resolver harness** (0.4) plus a **replayed generate** against an existing pack dir — it's faster and deterministic.

### 0.7 Capturing generate's output paths (needed by every full-run scenario)

`generate` prints its durable artifact locations. Capture them rather than guessing a `<session-id>`:

```bash
/eval-pack:generate 2>&1 | tee /tmp/uat-gen.log
ZIP=$(grep -oE 'Eval pack rendered to \S+' /tmp/uat-gen.log | awk '{print $NF}')
OPENDIR=$(grep -oE 'Open: file://\S+/index.html' /tmp/uat-gen.log | sed -E 's#Open: file://##; s#/index.html##')
echo "ZIP=$ZIP"; echo "OPENDIR=$OPENDIR"
[ -n "$ZIP" ] && [ -n "$OPENDIR" ] || echo "!! could not capture artifact paths — re-check generate output"
```

`$OPENDIR` is the openable copy (`<open_base>/eval-pack-<session_id>`, default under the system temp dir). `$ZIP` is the shipped zip. Use these two variables verbatim in later scenarios instead of a hand-built `<session-id>` path.

---

## 1. Prioritization (read before executing)

| Priority | Gate | Scenarios | Meaning |
|---|---|---|---|
| **P0** | Baseline regression | SC-BASE-01/02 | No-config output unchanged. **If this fails, the feature is not shippable.** |
| **P0** | Security no-leak | SC-SEC-01/02/03 | A planted secret must never reach any emitted artifact. |
| **P0** | Fail-loud | SC-NEG-01..14 | Every bad config halts non-zero with a clear message and writes nothing (and never proceeds on a stale artifact). |
| **P1** | Per-layer function | SC-CFG-*, SC-PRS-*, SC-LEN-01/04/05/06/07, SC-TPL-01/04, SC-ENV-* | Each knob does what it says; scripts fail cleanly across interpreters. |
| **P2** | Cosmetics & edges | SC-TPL-02/03/05/06/07, SC-LEN-02/03, SC-CFG-04/07/08/09/11/12/13, SC-SET-02/04/05/06 | Polish, documented-but-deferred behavior, low-severity hardening. |

A P0 failure blocks release. P1 failures block the *specific layer* they touch. P2 failures are logged and triaged.

---

## 2. Baseline Regression (P0 — the single most important gate)

### SC-BASE-01 — Resolver with no config yields defaults, writes nothing surprising

**Goal:** Prove absence of config = shipped defaults, and `read_config(None)` path is intact.

**Setup:** `uat_reset` (0.5). A repo with **no** `.eval-pack.json`, **no** `.eval-pack.local.json`, and **no** `CLAUDE_PLUGIN_OPTION_*` env vars set (`env | grep CLAUDE_PLUGIN_OPTION` must be empty).

**Steps:**
```bash
cd /tmp/uat-target
env | grep CLAUDE_PLUGIN_OPTION   # expect: no output
python3 ~/Code/eval-pack/scripts/resolve_config.py "$(pwd)" /tmp/uat-pack ; echo "exit=$?"
python3 - <<'PY'
import json
c=json.load(open("/tmp/uat-pack/eval-config.json"))
for k,exp in {"scopeDriftFileThreshold":10,"retryAmberThreshold":4,"skillArgsMaxLen":200,
  "publishOpenable":True,"analysisStance":"skeptical-reviewer","verdictAggregation":"core",
  "brandName":"Eval Pack","subjectNoun":"extension","defaultTheme":"dark"}.items():
    assert c[k]==exp, (k,c[k])
assert c["redaction"]==[] and c["analysisLenses"]==[] and c["sections"]==[]
print("BASELINE DEFAULTS OK")
PY
```

**Expected:** `exit=0`; `resolved config -> /tmp/uat-pack/eval-config.json`; script prints `BASELINE DEFAULTS OK`.

**Pass/Fail:** PASS iff `exit=0` and every default matches (script prints `BASELINE DEFAULTS OK`). Any mismatch or non-zero exit = FAIL.

### SC-BASE-02 — Full no-config generate is structurally identical to `main`

**Goal:** The rendered report with empty config is structurally identical to `main`. Because `index.html` embeds a per-run `window.__EVAL_PACK_DATA__` blob (and the tab title now reflects the analysis title), a raw byte diff is meaningless; use the structural procedure below so "identical" is falsifiable.

**Setup:** `uat_reset`. Produce a report on `main` and on `feat/config-foundation` from the **same** conversation. Since the data blob differs by run, comparison is over static chrome only.

**Steps:**
1. On `main`: `/eval-pack:generate`; unzip to `/tmp/uat-main`.
2. On `feat/config-foundation` (no config files): `/eval-pack:generate`; unzip to `/tmp/uat-feat`.
3. Compare the **static template**, not the data:
```bash
# a) template files should be structurally equal (config-gated branches are the only allowed delta):
diff <(git show main:templates/html/scripts.js) \
     <(git show feat/config-foundation:templates/html/scripts.js) | head -60
# b) tab set: same buttons, same order, same active tab
for d in /tmp/uat-main /tmp/uat-feat; do
  echo "== $d =="; grep -oE 'data-tab="[^"]+"' "$d"/*/index.html 2>/dev/null || \
    grep -oE 'data-tab="[^"]+"' "$d"/index.html
done
# c) chrome strings: logo text, footer, heading noun
for d in /tmp/uat-main /tmp/uat-feat; do
  echo "== $d =="; grep -oE 'Eval Pack|extension|<footer[^>]*>[^<]*' "$d"/*/index.html 2>/dev/null \
    | sort -u
done
```
4. Open `/tmp/uat-feat/**/index.html` in a browser; visually confirm logo, footer, headings, theme, tab set.

**Expected:**
- Tab set (b): identical button list, identical order, no **Lenses** tab on either.
- Chrome strings (c): logo reads **Eval Pack**; footer unchanged; headings use the word **extension**; identical set on both branches.
- Theme is **dark** (no `data-theme` forced; static CSS default applies).
- Template diff (a): only config-gated additions (new branches guarded by config that is empty/default); no change to existing structure.
- *Acknowledged known deviation:* the browser tab title may now reflect the analysis title rather than the static "Eval Pack" (template audit, low). This is **why** a byte diff is not used. Record whether product accepts this; it is a **P2 note**, not a blocker, but must be **noticed here**, not discovered later.

**Pass/Fail:** PASS iff (b) and (c) are identical across branches, theme is dark, no Lenses tab, and (a) shows only config-gated additions. Any Lenses tab, any theme change, any wording change, or any structural (non-config-gated) template change = FAIL.

---

## 3. Config Resolution & Fail-Loud (P0/P1)

> All scenarios here use the resolver harness (0.4). Run `uat_reset` (0.5) before **each**.

### SC-CFG-01 — Full precedence chain, env final (P1)

**Goal:** default < extends-preset < `.eval-pack.json` < `.eval-pack.local.json` < env, and env is final.

**Setup:** `uat_reset`, then:
```bash
cd /tmp/uat-target
cat > team-preset.json <<'JSON'
{ "scopeDriftFileThreshold": 5, "retryAmberThreshold": 2, "subjectNoun": "preset-noun" }
JSON
cat > .eval-pack.json <<'JSON'
{ "extends": ["team-preset.json"], "scopeDriftFileThreshold": 7, "subjectNoun": "project-noun" }
JSON
cat > .eval-pack.local.json <<'JSON'
{ "scopeDriftFileThreshold": 9 }
JSON
```

**Steps:**
```bash
CLAUDE_PLUGIN_OPTION_scopeDriftFileThreshold=99 \
  python3 ~/Code/eval-pack/scripts/resolve_config.py "$(pwd)" /tmp/uat-pack ; echo "exit=$?"
python3 - <<'PY'
import json;c=json.load(open("/tmp/uat-pack/eval-config.json"))
assert c["scopeDriftFileThreshold"]==99, c["scopeDriftFileThreshold"]   # env wins
assert c["retryAmberThreshold"]==2, c["retryAmberThreshold"]            # preset-only key retained
assert c["subjectNoun"]=="project-noun", c["subjectNoun"]               # project beats preset
print("PRECEDENCE OK")
PY
```

**Expected:** `exit=0`, `PRECEDENCE OK`.
**Pass/Fail:** PASS iff env=99, preset-only key=2, project noun wins. Cleanup via `uat_reset`.

### SC-CFG-01b — Local layer beats project **in isolation** (P1)

**Goal:** SC-CFG-01 masks the local layer under env=99, so "`.eval-pack.local.json` beats `.eval-pack.json`" is never actually observed. Prove it with **no env override present**.

**Setup:** `uat_reset`, then:
```bash
cat > .eval-pack.json       <<'JSON'
{ "scopeDriftFileThreshold": 7, "subjectNoun": "project-noun" }
JSON
cat > .eval-pack.local.json <<'JSON'
{ "scopeDriftFileThreshold": 9 }
JSON
```
**Steps:**
```bash
env | grep CLAUDE_PLUGIN_OPTION && echo "!! env not clean, abort"   # must be empty
python3 ~/Code/eval-pack/scripts/resolve_config.py "$(pwd)" /tmp/uat-pack >/dev/null
python3 - <<'PY'
import json;c=json.load(open("/tmp/uat-pack/eval-config.json"))
assert c["scopeDriftFileThreshold"]==9, c["scopeDriftFileThreshold"]   # local beats project
assert c["subjectNoun"]=="project-noun", c["subjectNoun"]              # project key untouched by local
print("LOCAL-OVER-PROJECT OK")
PY
```
**Expected:** `scopeDriftFileThreshold==9`, `subjectNoun=="project-noun"`.
**Pass/Fail:** PASS iff local overrides the project scalar while leaving keys the local layer did not set intact. Cleanup via `uat_reset`.

### SC-CFG-02 — List concat-dedupe (files) vs env-replace (P1)

**Goal:** File layers append+dedupe list keys; env **replaces** the list.

**Setup:** `uat_reset`, then `.eval-pack.json` = `{ "frictionCategories": ["tooling","structure","tooling"] }`.
**Steps:**
```bash
python3 ~/Code/eval-pack/scripts/resolve_config.py "$(pwd)" /tmp/uat-pack >/dev/null
python3 -c 'import json;print(json.load(open("/tmp/uat-pack/eval-config.json"))["frictionCategories"])'
# expect the default list with tooling/structure appended & deduped, e.g.
# ['tooling','structure','naming','docs','other']  (order: defaults first, dedupe applied)

CLAUDE_PLUGIN_OPTION_frictionCategories="a,,b,a" \
  python3 ~/Code/eval-pack/scripts/resolve_config.py "$(pwd)" /tmp/uat-pack >/dev/null
python3 -c 'import json;print(json.load(open("/tmp/uat-pack/eval-config.json"))["frictionCategories"])'
# expect exactly ['a','b']  (comma-split, empties dropped, list REPLACED)
```
**Expected/Pass:** file layer = deduped union (no `tooling` twice, defaults retained); env = `['a','b']` exactly. Any other shape = FAIL. Cleanup via `uat_reset`.

### SC-CFG-03 — `--check` validates without writing (P1)

**Setup:** `uat_reset`; valid `.eval-pack.json` = `{ "retryAmberThreshold": 3 }`.
**Steps:**
```bash
rm -f /tmp/uat-pack/eval-config.json
python3 ~/Code/eval-pack/scripts/resolve_config.py "$(pwd)" --check ; echo "exit=$?"
ls /tmp/uat-pack/eval-config.json 2>&1
```
**Expected:** stdout `config valid`, `exit=0`, and `eval-config.json` **absent**.
**Pass/Fail:** PASS iff prints `config valid`, exit 0, no file written.

### SC-CFG-04 — DEFAULTS non-aliasing (P2)

**Goal:** Resolving twice with mutation cannot corrupt defaults (already unit-covered; a spot-check).
**Steps:** Run SC-CFG-02 file case, then `uat_reset` + SC-BASE-01; confirm baseline defaults are still pristine.
**Pass/Fail:** PASS iff SC-BASE-01 still passes after prior scenarios.

### SC-CFG-05 — extends → missing / typo'd / case-wrong preset (P0 fail-loud target) ⚠️ anchors config-core HIGH risk

**Goal:** A rename, typo, or case-mismatch of an `extends` target must NOT silently no-op to defaults.

**Setup:** `uat_reset`, then `.eval-pack.json` = `{ "extends": ["team-preset-DOES-NOT-EXIST.json"], "retryAmberThreshold": 3 }`.
**Steps (missing file):**
```bash
python3 ~/Code/eval-pack/scripts/resolve_config.py "$(pwd)" /tmp/uat-pack ; echo "exit=$?"
ls /tmp/uat-pack/eval-config.json 2>&1
```
**Steps (case-wrong, case-insensitive filesystems like default macOS):**
```bash
uat_reset
echo '{ "retryAmberThreshold": 2 }' > team-preset.json
echo '{ "extends": ["Team-Preset.json"] }' > .eval-pack.json   # wrong case
python3 ~/Code/eval-pack/scripts/resolve_config.py "$(pwd)" /tmp/uat-pack ; echo "exit=$?"
python3 -c 'import json;print(json.load(open("/tmp/uat-pack/eval-config.json"))["retryAmberThreshold"])' 2>/dev/null
```

**Expected (intended behavior):** *both* cases → non-zero exit and a stderr message naming the unresolved preset; **no** `eval-config.json` written.
- Missing-file case: stderr names `team-preset-DOES-NOT-EXIST.json`.
- Case-wrong case: EITHER (a) the tool resolves the file case-insensitively and applies it (prints `2`, exit 0 — acceptable *only if* documented as case-insensitive), OR (b) it refuses with a stderr message naming `Team-Preset.json`. What is **NOT** acceptable: exit 0 with `retryAmberThreshold==4` (the default), i.e. the preset silently vanished.

**Current known behavior (per audit — likely FAIL):** `_read_json` returns `{}` for a missing file, so the missing-file case **exits 0** and silently resolves to defaults+project. If you observe `exit=0` and a written `eval-config.json` (with `retryAmberThreshold` at the default), **record this as a P0 defect** (Silent Fallback: the entire `extends` feature can vanish on a rename with zero signal), filed against `scripts/config.py:load_config` extends loop.

**Pass/Fail:** PASS only if the missing-file case refuses (non-zero, actionable stderr, no file) AND the case-wrong case either applies the preset (documented case-insensitive) or refuses — never silently drops to defaults. Any silent default resolution = FAIL (P0).

### SC-CFG-06 — Boolean env garbage / false-y strings (P0 fail-loud target) ⚠️ anchors config-core HIGH risk

**Goal:** A typo in a boolean env override must not silently DISABLE a feature.

**Setup:** `uat_reset`.
**Steps:**
```bash
# 1) garbage truthy typo
CLAUDE_PLUGIN_OPTION_publishOpenable=banana \
  python3 ~/Code/eval-pack/scripts/resolve_config.py "$(pwd)" /tmp/uat-pack ; echo "exit=$?"
  python3 -c 'import json;print("publishOpenable=",json.load(open("/tmp/uat-pack/eval-config.json"))["publishOpenable"])' 2>/dev/null
# 2) explicit false-y forms
for v in False FALSE 0 no off; do
  CLAUDE_PLUGIN_OPTION_publishOpenable=$v \
   python3 ~/Code/eval-pack/scripts/resolve_config.py "$(pwd)" /tmp/uat-pack >/dev/null
  python3 -c "import json;print('$v ->',json.load(open('/tmp/uat-pack/eval-config.json'))['publishOpenable'])"
done
```
**Expected/Known:** `False/FALSE/0/no/off` → `False` (correct). `banana` → **`False`** today, which means a **misspelled truthy value silently turns the feature off** — asymmetric with the int path (which raises). The intended contract (confirm with product) should require garbage to **raise** like int does. If product wants fail-loud parity and `banana` yields a silent `False`, this is a **P0 defect** at `scripts/config.py:_coerce`.

**Pass/Fail:** PASS iff false-y strings map to `False` AND garbage either raises (non-zero exit, stderr names the bad value) or is documented as intentionally false. A truthy typo that silently disables the feature with no signal, where product expected fail-loud = FAIL (P0).

### SC-CFG-07 — Misspelled env-override key silently ignored (P2) ⚠️ anchors config-core MEDIUM

**Setup:** `uat_reset`.
**Steps:**
```bash
CLAUDE_PLUGIN_OPTION_scopeDriftThreshold=3 \
  python3 ~/Code/eval-pack/scripts/resolve_config.py "$(pwd)" /tmp/uat-pack >/dev/null
python3 -c 'import json;print(json.load(open("/tmp/uat-pack/eval-config.json"))["scopeDriftFileThreshold"])'
# correct key is scopeDriftFileThreshold; the typo has NO effect -> prints 10 (default)
CLAUDE_PLUGIN_OPTION_scopeDriftFileThreshold=3 \
  python3 ~/Code/eval-pack/scripts/resolve_config.py "$(pwd)" /tmp/uat-pack >/dev/null
python3 -c 'import json;print(json.load(open("/tmp/uat-pack/eval-config.json"))["scopeDriftFileThreshold"])'
# correct key -> prints 3
```
**Expected/Known:** typo'd env var silently ignored (prints `10`); correct var takes effect (prints `3`). Record silent-ignore of typos as a documentation/UX risk (no unknown-env-key detection to mirror the file path's unknown-key check).
**Pass/Fail:** PASS iff the correct key works AND the typo is inert; log the typo silent-ignore for triage.

### SC-CFG-08 — Dict-replace vs list-concat merge asymmetry (P2) ⚠️ anchors config-core MEDIUM

**Goal:** Make the tester confront that `messages`/`rubric` **replace** while list keys **append**, and that `sections` is append-only.

**Setup:** `uat_reset`, then:
```bash
cat > base-preset.json <<'JSON'
{ "messages": {"a":"1"}, "sections": ["summary","tools","tests"] }
JSON
cat > .eval-pack.json <<'JSON'
{ "extends":["base-preset.json"], "messages": {"b":"2"}, "sections": ["metrics"] }
JSON
```
**Steps:**
```bash
python3 ~/Code/eval-pack/scripts/resolve_config.py "$(pwd)" /tmp/uat-pack >/dev/null
python3 -c 'import json;c=json.load(open("/tmp/uat-pack/eval-config.json"));print("messages=",c["messages"]);print("sections=",c["sections"])'
```
**Expected/Known:** `messages` = `{"b":"2"}` (preset entry `a` **lost** — whole-dict replace). `sections` = `["summary","tools","tests","metrics"]` (append-only; the project layer **cannot** reorder or drop an inherited section). Confirm this matches product intent. If a config author would reasonably expect merge-for-messages or reorder-for-sections, record as a Leaky Narrative defect (must read source to know the rule).
**Pass/Fail:** Behavioral PASS iff observed matches the above; flag intent mismatch for product. Cleanup via `uat_reset`.

### SC-CFG-09 — analysisStanceText round-trip asymmetry (P2) ⚠️ anchors config-core MEDIUM

**Goal:** The resolver injects `analysisStanceText`, but `validate()` doesn't know that key — confirm nothing downstream re-validates the emitted file.

**Setup:** `uat_reset`.
**Steps:**
```bash
python3 ~/Code/eval-pack/scripts/resolve_config.py "$(pwd)" /tmp/uat-pack >/dev/null
python3 -c 'import json;print("analysisStanceText present:", "analysisStanceText" in json.load(open("/tmp/uat-pack/eval-config.json")))'
python3 - <<'PY'
import sys;sys.path.insert(0,"/Users/jasonsmith/Code/eval-pack/scripts")
import config,json
errs=config.validate(json.load(open("/tmp/uat-pack/eval-config.json")))
print("re-validate errors:",errs)
PY
```
**Expected:** `analysisStanceText present: True`; re-validate reports `unknown config key: 'analysisStanceText'`. This is **fine only because** the real consumer is `read_config` (which does NOT validate). Verify no generate step calls `validate()` on the emitted `eval-config.json`. If any does, it will reject the resolver's own output — file as defect.
**Pass/Fail:** PASS iff the field is present and no downstream step re-validates the emitted file.

### SC-CFG-11 — Empty / whitespace-only / `{}` config vs absent file (P2)

**Goal:** Distinguish three cases the "absent = defaults" contract can trap on: an **absent** file (defaults), an **empty/whitespace** file (`json.loads('')` raises → must fail loud, NOT silently default), and an explicit **`{}`** file (defaults).

**Setup/Steps:**
```bash
# a) absent -> defaults (baseline)
uat_reset
python3 ~/Code/eval-pack/scripts/resolve_config.py "$(pwd)" /tmp/uat-pack ; echo "absent exit=$?"

# b) zero-byte file
uat_reset; : > .eval-pack.json
python3 ~/Code/eval-pack/scripts/resolve_config.py "$(pwd)" /tmp/uat-pack ; echo "empty exit=$?"

# c) whitespace-only file
uat_reset; printf '   \n\t' > .eval-pack.json
python3 ~/Code/eval-pack/scripts/resolve_config.py "$(pwd)" /tmp/uat-pack ; echo "ws exit=$?"

# d) explicit empty object
uat_reset; printf '{}' > .eval-pack.json
python3 ~/Code/eval-pack/scripts/resolve_config.py "$(pwd)" /tmp/uat-pack ; echo "empty-obj exit=$?"
python3 -c 'import json;print(json.load(open("/tmp/uat-pack/eval-config.json"))["retryAmberThreshold"])'
```
**Expected:**
- (a) exit 0, defaults written.
- (b)/(c) exit **non-zero**, stderr `.eval-pack.json: invalid JSON (…)` — an empty/whitespace file is a malformed file, **not** an absent one, and must fail loud rather than masquerade as "no config". (If the tool instead treats empty-string as `{}`/defaults, that is acceptable **only if** documented; a silent default here is a UX trap — record it.)
- (d) exit 0, `retryAmberThreshold` prints `4` (defaults).
**Pass/Fail:** PASS iff absent and `{}` yield defaults, AND empty/whitespace either fails loud with an invalid-JSON message or is explicitly documented as defaults. A silent, undocumented default for a corrupt/empty file = FAIL.

### SC-CFG-12 — Nested / multiple / traversal `extends` (P2)

**Goal:** Pin down three under-specified `extends` behaviors.

**Setup/Steps:**

(a) **Preset that itself declares `extends`** (dropped by `_strip_meta`?):
```bash
uat_reset
echo '{ "retryAmberThreshold": 1 }' > base-preset.json
echo '{ "extends": ["base-preset.json"], "retryAmberThreshold": 2 }' > mid-preset.json
echo '{ "extends": ["mid-preset.json"] }' > .eval-pack.json
python3 ~/Code/eval-pack/scripts/resolve_config.py "$(pwd)" /tmp/uat-pack ; echo "exit=$?"
python3 -c 'import json;print("retryAmber=",json.load(open("/tmp/uat-pack/eval-config.json"))["retryAmberThreshold"])' 2>/dev/null
```
Expected: if nested `extends` is intentionally **not** recursive, `mid-preset`'s own `extends` is stripped and `base-preset` never loads → `retryAmberThreshold==2` (mid's own value), exit 0. This is acceptable **only if** documented as single-level. If a config author would expect `base-preset` to apply (`1`), record a Leaky Narrative defect. What is NOT acceptable: silent partial application or a crash.

(b) **Multiple presets in one list — later wins:**
```bash
uat_reset
echo '{ "retryAmberThreshold": 1, "subjectNoun": "first" }'  > base-preset.json
echo '{ "retryAmberThreshold": 2 }'                          > mid-preset.json
echo '{ "extends": ["base-preset.json","mid-preset.json"] }' > .eval-pack.json
python3 ~/Code/eval-pack/scripts/resolve_config.py "$(pwd)" /tmp/uat-pack >/dev/null
python3 -c 'import json;c=json.load(open("/tmp/uat-pack/eval-config.json"));print(c["retryAmberThreshold"],c["subjectNoun"])'
```
Expected: `2 first` — later preset in the list overrides the earlier on the shared key (`retryAmberThreshold`), earlier-only key (`subjectNoun`) retained. Record the observed precedence if it differs.

(c) **Traversal / absolute preset path:**
```bash
uat_reset
echo '{ "extends": ["../../etc/hostname"] }' > .eval-pack.json
python3 ~/Code/eval-pack/scripts/resolve_config.py "$(pwd)" /tmp/uat-pack ; echo "exit=$?"
echo '{ "extends": ["/etc/hostname"] }' > .eval-pack.json
python3 ~/Code/eval-pack/scripts/resolve_config.py "$(pwd)" /tmp/uat-pack ; echo "exit=$?"
```
Expected: a `../` traversal or absolute path either (i) is rejected/confined to the project root with an actionable stderr, or (ii) is read but fails loud as invalid JSON. What is NOT acceptable: a traceback, or silently reading a file outside the repo and applying garbage. Record actual behavior; a resolvable path escape is a hardening defect (author-controlled config, low severity).

**Pass/Fail:** PASS iff (a) matches documented single-level semantics, (b) shows a deterministic later-wins order, and (c) neither crashes nor silently escapes the repo. Log any Leaky Narrative / traversal finding.

### SC-CFG-13 — Negative / zero numeric thresholds (P2)

**Goal:** `_TYPES` has no range check; `scopeDriftFileThreshold=0/-1`, `retryAmberThreshold=0`, `skillArgsMaxLen=0/-5` pass `validate()`. Pin the behavior so it is not "undefined".

**Setup/Steps:**
```bash
for k in scopeDriftFileThreshold retryAmberThreshold skillArgsMaxLen; do
  for val in 0 -1; do
    uat_reset; printf '{ "%s": %s }' "$k" "$val" > .eval-pack.json
    python3 ~/Code/eval-pack/scripts/resolve_config.py "$(pwd)" /tmp/uat-pack ; echo "$k=$val exit=$?"
    python3 -c "import json;print('  resolved',json.load(open('/tmp/uat-pack/eval-config.json'))['$k'])" 2>/dev/null
  done
done
```
Then run one **full generate** with `{ "skillArgsMaxLen": 0 }` on a conversation that invokes a Skill, and inspect `tools.json`:
```bash
python3 -c 'import json,glob;print([t.get("args") for t in json.load(open(sorted(glob.glob("'$OPENDIR'/tools.json"))[0])).get("tools",[])][:5])'
```
**Expected/Known:** resolve accepts all values with exit 0 (no range validation). At runtime, negative/zero thresholds must **not crash** downstream (`detect_patterns`, `extract_tools`). Document the effective behavior of each: e.g. `skillArgsMaxLen=0` truncates args to empty string (acceptable) vs. raises/produces negative-slice garbage (defect). A crash or a nonsensical slice = defect; record severity. Product should decide whether a range check (`>=1`) belongs at `validate()` — record as a hardening recommendation.
**Pass/Fail:** PASS iff every value resolves without error AND runtime behavior is non-crashing and explainable; FAIL on any traceback or garbage output (e.g. Python negative-index wrap silently keeping the tail of an arg).

---

## 4. Failure / Negative Paths (P0 — every one must halt non-zero, write nothing, never reuse a stale artifact)

For each: **exit code must be non-zero, stderr must carry an actionable message, and `/tmp/uat-pack/eval-config.json` must NOT be created/updated.** Run `uat_reset` (0.5) before each row so no stray `.eval-pack.local.json` or `CLAUDE_PLUGIN_OPTION_*` from a prior scenario masks the error, then delete any stale output: `rm -f /tmp/uat-pack/eval-config.json`.

| ID | Config to write in `.eval-pack.json` (or env) | Expected stderr substring |
|---|---|---|
| **SC-NEG-01** unknown key | `{ "notAKey": 1 }` | `unknown config key: 'notAKey'` |
| **SC-NEG-02** wrong type | `{ "scopeDriftFileThreshold": "ten" }` | `scopeDriftFileThreshold: expected int, got str` |
| **SC-NEG-03** bool-for-int | `{ "retryAmberThreshold": true }` | `retryAmberThreshold: expected int, got bool` |
| **SC-NEG-04** malformed JSON | `{ "retryAmberThreshold": 3,, }` | `.eval-pack.json: invalid JSON (` |
| **SC-NEG-05** uncoercible int env | env `CLAUDE_PLUGIN_OPTION_retryAmberThreshold=abc` | `CLAUDE_PLUGIN_OPTION_retryAmberThreshold: expected int, got 'abc'` |
| **SC-NEG-06** unknown stance | `{ "analysisStance": "grumpy-uncle" }` | `unknown analysisStance 'grumpy-uncle' — no preset at presets/stances/grumpy-uncle.md` |
| **SC-NEG-07** bad redaction regex | `{ "redaction": ["a[b"] }` | `redaction: invalid regex 'a[b' (` |
| **SC-NEG-08** unknown aggregation | `{ "verdictAggregation": "median" }` | `verdictAggregation: 'median' is not one of ['core', 'min', 'mean']` |
| **SC-NEG-09** unknown theme | `{ "defaultTheme": "sepia" }` | `defaultTheme: 'sepia' is not one of ['dark', 'light', 'system']` |
| **SC-NEG-10** malformed lens | `{ "analysisLenses": [{"role":"scorer"}] }` | `analysisLenses[0]: must be an object with a 'skill'` |
| **SC-NEG-11** bad lens role | `{ "analysisLenses": [{"skill":"x","role":"boss"}] }` | `analysisLenses[0]: role must be 'contributor' or 'scorer'` |
| **SC-NEG-13** dict key via env (string coercion) | env `CLAUDE_PLUGIN_OPTION_messages=hello` | `messages: expected dict, got str` |

**Runner (per row):**
```bash
uat_reset
rm -f /tmp/uat-pack/eval-config.json
printf '%s' '<config json here>' > .eval-pack.json     # OR: set the env var inline (see below)
python3 ~/Code/eval-pack/scripts/resolve_config.py "$(pwd)" /tmp/uat-pack ; echo "exit=$?"
ls /tmp/uat-pack/eval-config.json 2>&1     # must say "No such file"
```
For env rows (SC-NEG-05, SC-NEG-13), instead run inline, e.g.:
```bash
uat_reset; rm -f /tmp/uat-pack/eval-config.json
CLAUDE_PLUGIN_OPTION_messages=hello \
  python3 ~/Code/eval-pack/scripts/resolve_config.py "$(pwd)" /tmp/uat-pack ; echo "exit=$?"
ls /tmp/uat-pack/eval-config.json 2>&1
```
**Pass/Fail per row:** PASS iff `exit` is non-zero, stderr contains the substring, and **no** `eval-config.json` exists afterward. Any silent success or written file = FAIL (P0).

**SC-NEG-13 note (dict-key env coercion):** `_coerce` returns a raw **string** for a dict-typed key like `messages`/`rubric`; the fail-loud parity with the int path holds only if `validate()` then rejects `expected dict, got str`. If instead the string is silently stored (so `messages` becomes `"hello"` downstream), that is a defect — record it.

**SC-NEG-12 — generate/setup honor the halt (P0):** `uat_reset`, then introduce SC-NEG-01's bad key, run `/eval-pack:setup` (Step 5 `--check`) and `/eval-pack:generate` (Step 0.7). Both must **STOP** and surface the stderr error, not silently fall back to defaults. **Pass/Fail:** PASS iff both halt with the error; a produced report = FAIL (P0).

**SC-NEG-14 — a failing resolve must not proceed on a STALE `eval-config.json` (P0):** Fail-loud is only real if a prior good artifact cannot be silently reused.
```bash
uat_reset
# 1) seed a VALID resolved artifact:
echo '{ "retryAmberThreshold": 3 }' > .eval-pack.json
python3 ~/Code/eval-pack/scripts/resolve_config.py "$(pwd)" /tmp/uat-pack >/dev/null
test -f /tmp/uat-pack/eval-config.json && echo "seeded"
# 2) now break the config and re-resolve into the SAME pack dir:
echo '{ "notAKey": 1 }' > .eval-pack.json
python3 ~/Code/eval-pack/scripts/resolve_config.py "$(pwd)" /tmp/uat-pack ; echo "exit=$?"
# 3) the stale-but-valid file must NOT be treated as this run's config:
python3 -c 'import json;print("retryAmberThreshold=",json.load(open("/tmp/uat-pack/eval-config.json"))["retryAmberThreshold"])'
```
**Expected:** step 2 exits non-zero with `unknown config key: 'notAKey'`. The emitted file must **not** silently remain the seeded `retryAmberThreshold: 3` such that a subsequent generate proceeds as if config were valid. Acceptable outcomes: the resolver overwrites nothing (leaving the stale file) **but** generate re-runs `--check` first and halts (verify by then running `/eval-pack:generate` → must STOP); OR the resolver truncates/removes the stale artifact on failure. NOT acceptable: resolve fails, the stale file persists, and generate proceeds on it.
**Pass/Fail:** PASS iff a broken resolve cannot cause generate to ship a report built on a stale/previous config. Verify by running `/eval-pack:generate` after step 2 and confirming it halts. Any report produced = FAIL (P0).

---

## 5. Security / Redaction Acceptance (P0)

> This is the highest-consequence section. The audit found redaction is applied to **only** `transcript.html` and `transcript.jsonl`, and **not** to derived JSON artifacts. SC-SEC-01 is designed to catch exactly that.

### The planted secret

Use a distinctive, greppable token so any leak is unambiguous:
```
SECRET_TOKEN = "AKIA-UAT-LEAK-0xDEADBEEF"
```
Redaction rule to configure:
```json
{ "redaction": ["AKIA-UAT-LEAK-[0-9A-Fa-fx]+"], "publishOpenable": true }
```

### SC-SEC-01 — Secret must be absent from EVERY emitted artifact ⚠️ anchors security CRITICAL

**Goal:** Prove the no-leak invariant covers derived artifacts, not just the two transcript files.

**Setup:** `uat_reset`. In `/tmp/uat-target`, write `.eval-pack.json` with the redaction rule above. Ensure the secret lands in **multiple** artifact-producing paths:
- **Transcript:** paste `AKIA-UAT-LEAK-0xDEADBEEF` into a conversation turn.
- **analysis.json:** phrase the conversation so the evaluator is likely to quote the token back (e.g. "review this credential: AKIA-UAT-LEAK-0xDEADBEEF").
- **tools.json:** invoke a Skill or reference an agent whose arg/description contains the token, so it's captured in tool metadata.
- **patterns/metrics:** the token in a matched snippet.

**Steps:** Run generate and capture the real paths (0.7), then grep the **authoritative durable artifacts** (`$OPENDIR`, `$ZIP`) — no guessed `<session-id>`:
```bash
/eval-pack:generate 2>&1 | tee /tmp/uat-gen.log
ZIP=$(grep -oE 'Eval pack rendered to \S+' /tmp/uat-gen.log | awk '{print $NF}')
OPENDIR=$(grep -oE 'Open: file://\S+/index.html' /tmp/uat-gen.log | sed -E 's#Open: file://##; s#/index.html##')
echo "ZIP=$ZIP OPENDIR=$OPENDIR"
[ -n "$ZIP" ] && [ -n "$OPENDIR" ] || { echo "!! path capture failed"; }

# 1) the openable copy (the exact dir generate printed — no guessing):
echo "=== openable copy files ==="; find "$OPENDIR" -type f
grep -rnI "AKIA-UAT-LEAK" "$OPENDIR" && { echo ">>> LEAK IN OPENABLE COPY <<<"; LEAK=1; } || echo "openable clean"

# 2) the shipped zip:
rm -rf /tmp/uat-unzip && unzip -o "$ZIP" -d /tmp/uat-unzip >/dev/null
grep -rnI "AKIA-UAT-LEAK" /tmp/uat-unzip && { echo ">>> LEAK IN ZIP <<<"; LEAK=1; } || echo "zip clean"

echo "OVERALL: ${LEAK:+FAIL — leak found}"; : "${LEAK:=0}"; [ "$LEAK" = 0 ] && echo "OVERALL: clean"
```
Explicitly confirm the grep covered each of these filenames in **both** `$OPENDIR` and `/tmp/uat-unzip` (they must appear in `find` output and be clean): `transcript.html`, `transcript.jsonl`, `analysis.json`, `metrics.json`, `patterns.json`, `test-results.json`, `tools.json`, `lenses.json`, `data.json`, and `index.html` (the `window.__EVAL_PACK_DATA__` blob).

**Expected (intended):** `AKIA-UAT-LEAK` appears in **zero** files across the openable copy and the zip; the final line prints `OVERALL: clean`.

**Known risk (per audit — likely FAIL for derived artifacts):** the token is expected to be masked in `transcript.html`/`transcript.jsonl` but to **survive** in `analysis.json`, `tools.json`, `data.json`, and `index.html`. If `grep` finds the token in any derived artifact, this is a **P0 CRITICAL leak** filed against `scripts/render_html.py` (redaction choke points cover only the two transcript files while `write_zip` rglobs and `publish_openable` copytrees the whole dir).

**Pass/Fail:** PASS iff the token is absent from every file in `$OPENDIR` **and** `/tmp/uat-unzip` (final line `OVERALL: clean`). Any hit = FAIL, blocks release.

### SC-SEC-02 — openableDir edge cases: in-repo, nonexistent, unwritable, `~`, absolute-outside (P0/P1) ⚠️ anchors security HIGH

**Goal:** An openable copy must never become a committable leak vector, and a bad `openableDir` must fail cleanly, not crash.

**Setup/Steps — each is a separate `uat_reset` run; all use the SC-SEC-01 redaction rule and a planted secret:**

(a) **In-repo (P0):** `.eval-pack.json` adds `"openableDir": "./public"`.
```bash
/eval-pack:generate
find /tmp/uat-target/public -type f 2>/dev/null
git -C /tmp/uat-target status --porcelain
git -C /tmp/uat-target check-ignore public/ ; echo "ignored=$?"   # 0 means gitignored
grep -rnI "AKIA-UAT-LEAK" /tmp/uat-target/public && echo ">>> COMMITTABLE LEAK <<<"
```
Expected: either the tool **refuses** an in-repo `openableDir` (non-zero, actionable stderr), OR the copy is gitignored **and** fully redacted. A committable, non-ignored `./public` containing artifacts (unredacted per SC-SEC-01) = **P0 FAIL**, filed against `render_html.py` openableDir bounds-check.

(b) **Nonexistent parent (P1):** `"openableDir": "/tmp/uat-does-not-exist-xyz/pub"`.
Expected: generate either creates the dir tree (`open_base.mkdir(parents=True)`) and writes the copy, or fails with an actionable "cannot create openable dir" message. A traceback = FAIL.

(c) **Unwritable dir (P1):**
```bash
mkdir -p /tmp/uat-ro && chmod 000 /tmp/uat-ro
# .eval-pack.json: "openableDir": "/tmp/uat-ro/pub"
/eval-pack:generate 2>&1 | tail -5
chmod 755 /tmp/uat-ro
```
Expected: the zip is still produced (durable artifact), and the openable-copy failure is a **loud Warning** naming the path (per render_html's `Warning: could not write openable copy: …`), NOT a hard crash that loses the zip. Verify `$ZIP` exists. A lost zip or a raw traceback = FAIL.

(d) **`~` expansion (P1):** `"openableDir": "~/uat-open"`.
Expected: `~` either expands to `$HOME/uat-open` OR is treated as a literal `./~` dir — confirm which, and confirm no crash. Record whether tilde-expansion is supported; an unexpanded literal `~` dir is a P2 UX note.

(e) **Absolute path outside repo (P1):** `"openableDir": "/tmp/uat-open-abs"`.
Expected: writes the copy there; confirm it is fully redacted (SC-SEC-01 grep) and outside any git tree.

**Pass/Fail:** PASS iff (a) produces no committable/unredacted in-repo artifact; (b)–(e) each either succeed cleanly or fail with a loud actionable message while preserving the zip; and no case crashes with a traceback.

### SC-SEC-03 — Malformed regex in `eval-config.json` bypassing the `--check` gate (P0) ⚠️ anchors security MEDIUM

**Goal:** A hand-edited `eval-config.json` with a bad regex must fail with an actionable message and leave **no** un-redacted `transcript.jsonl` behind.

**Setup:** `uat_reset`. Produce a valid pack, then hand-corrupt the resolved file:
```bash
python3 - <<'PY'
import json,glob
p=glob.glob("/tmp/uat-pack/eval-config.json")[0]
c=json.load(open(p)); c["redaction"]=["a[b"]; json.dump(c,open(p,"w"))
print("corrupted",p)
PY
```
Then re-run the render step (via `/eval-pack:generate` replay against the same pack, or invoke `render_html.py` directly per the SKILL's render Step).

**Steps:** run render; observe exit and stderr; then:
```bash
find /tmp/uat-target -name transcript.jsonl -exec grep -lI "AKIA-UAT-LEAK" {} \; 2>/dev/null
find "${OPENDIR%/*}" -maxdepth 2 -name transcript.jsonl -exec grep -lI "AKIA-UAT-LEAK" {} \; 2>/dev/null
```
**Expected/Known:** `read_config` does **not** validate, so the bad regex raises inside `redact` **outside** the transcript-loop try/except → an uncaught traceback (Black Box), fails closed (no zip) but may leave an **un-redacted `transcript.jsonl`** in `output_dir/<session_id>` because cleanup (`rmtree`) never runs. If you find a leftover jsonl containing the secret, that is a FAIL (residual un-redacted artifact on disk) plus a poor error message. Record whether the message is actionable ("invalid redaction regex 'a[b'") or a raw stack trace.
**Pass/Fail:** PASS iff the run halts with an actionable message AND no un-redacted `transcript.jsonl` remains on disk anywhere. Traceback + leftover jsonl = FAIL (P0).

### SC-SEC-04 — Secrets with HTML/JSON special characters (P1) ⚠️ anchors security MEDIUM

**Goal:** Redaction must survive serialization escaping (HTML-escape for `.html`, JSON-escape for `.jsonl`).

**Setup:** `uat_reset`. Plant secrets containing `&`, `<`, `"`, and a newline, e.g. `tok&sig=x`, `tok<v>`, `tok"q`. Write rules against the **natural** value:
```json
{ "redaction": ["tok&sig=x", "tok<v>", "tok\"q"] }
```
**Steps:** generate; capture `$OPENDIR`; grep the *shipped* `transcript.html` and `transcript.jsonl` for both the natural and the escaped forms:
```bash
for f in "$OPENDIR/transcript.html" "$OPENDIR/transcript.jsonl"; do
  echo "== $f =="
  grep -noE 'tok&sig|tok&amp;sig|tok<v>|tok&lt;v|tok"q|tok\\"q' "$f"
done
```
**Expected/Known:** A rule written against `tok&sig=x` may **fail to match** the escaped form `tok&amp;sig=x` in the HTML (and quote/newline-escaped forms in the jsonl), leaking the secret. Any escaped form of a planted secret appearing in output = leak. Record precisely which special-character secrets survive in which file.
**Pass/Fail:** PASS iff none of the planted secrets appear in either file in **any** form (natural or escaped). Any surviving form = FAIL (redaction-vs-escape ordering defect).

### SC-SEC-05 — Overlapping / ordered rules (P2) ⚠️ anchors security LOW

**Setup:** `uat_reset`; two rules, one broad one narrow, both targeting overlapping text: `{ "redaction": ["secret-[a-z]+", "secret-alpha-KEY"] }`, plant `secret-alpha-KEY` in the conversation.
**Steps:** generate; confirm every intended target is masked regardless of order.
**Expected:** all intended secrets masked; document if a broad earlier rule consumes text a later rule expected (rules apply sequentially over prior `[REDACTED]` substitutions).
**Pass/Fail:** PASS iff all targets masked. Log any order-sensitivity surprise.

### SC-SEC-06 — Empty rules & transcript-bundling flags (P1)

> Clarification: transcript bundling is controlled by **two** schema keys — `includeRawTranscript`
> (default `false`: bundle the raw machine-readable `transcript.jsonl`; off unless opted in) and
> `includeRenderedTranscript` (default `true`: render/bundle the human-readable `transcript.html`
> and its Transcript artifact link). Both are settable in `.eval-pack.json` and, for standalone
> renders without a resolved config, as `CLAUDE_PLUGIN_OPTION_includeRawTranscript` /
> `CLAUDE_PLUGIN_OPTION_includeRenderedTranscript` env flags.

**Setup/Steps:**

(a) **Empty redaction is a no-op, not a mangler:**
```bash
uat_reset
# run 1: no redaction key at all
/eval-pack:generate 2>&1 | tee /tmp/g1.log
O1=$(grep -oE 'Open: file://\S+/index.html' /tmp/g1.log | sed -E 's#Open: file://##; s#/index.html##')
cp "$O1/transcript.html" /tmp/t1.html; cp "$O1/transcript.jsonl" /tmp/t1.jsonl
uat_reset
echo '{ "redaction": [] }' > .eval-pack.json
/eval-pack:generate 2>&1 | tee /tmp/g2.log
O2=$(grep -oE 'Open: file://\S+/index.html' /tmp/g2.log | sed -E 's#Open: file://##; s#/index.html##')
# transcript bytes should be identical (same conversation); allow only run-id noise if any:
diff /tmp/t1.html "$O2/transcript.html" && echo "html identical" || echo "!! html differs"
diff /tmp/t1.jsonl "$O2/transcript.jsonl" && echo "jsonl identical" || echo "!! jsonl differs"
```
Expected: `redaction: []` produces `transcript.html`/`jsonl` byte-identical to the no-redaction run (no accidental masking/truncation). *Note:* this comparison is only valid if the two runs share the same transcript; if the harness cannot replay the identical transcript, restrict the check to "no `[REDACTED]` token appears and length is unchanged".

(b) **`includeRawTranscript` default (`false`) keeps the raw jsonl out; opting in bundles it:**
```bash
uat_reset
# default: includeRawTranscript unset -> false
/eval-pack:generate 2>&1 | tee /tmp/g3.log
Z3=$(grep -oE 'Eval pack rendered to \S+' /tmp/g3.log | awk '{print $NF}')
O3=$(grep -oE 'Open: file://\S+/index.html' /tmp/g3.log | sed -E 's#Open: file://##; s#/index.html##')
rm -rf /tmp/uz3 && unzip -o "$Z3" -d /tmp/uz3 >/dev/null
echo "jsonl in zip (expect none):";     find /tmp/uz3 -name '*.jsonl'
echo "jsonl in openable (expect none):"; find "$O3"   -name '*.jsonl'

uat_reset
echo '{ "includeRawTranscript": true }' > .eval-pack.json
/eval-pack:generate 2>&1 | tee /tmp/g4.log
Z4=$(grep -oE 'Eval pack rendered to \S+' /tmp/g4.log | awk '{print $NF}')
O4=$(grep -oE 'Open: file://\S+/index.html' /tmp/g4.log | sed -E 's#Open: file://##; s#/index.html##')
rm -rf /tmp/uz4 && unzip -o "$Z4" -d /tmp/uz4 >/dev/null
echo "jsonl in zip (expect present):";     find /tmp/uz4 -name '*.jsonl'
echo "jsonl in openable (expect present):"; find "$O4"   -name '*.jsonl'
```
Expected: with `includeRawTranscript` at its default (`false`), raw `*.jsonl` is **absent** from
both the zip and the openable copy. With `includeRawTranscript: true`, raw `*.jsonl` is **present**
in both.

(c) **`includeRenderedTranscript` default (`true`) bundles `transcript.html`; opting out drops it:**
```bash
uat_reset
# default: includeRenderedTranscript unset -> true
/eval-pack:generate 2>&1 | tee /tmp/g5.log
O5=$(grep -oE 'Open: file://\S+/index.html' /tmp/g5.log | sed -E 's#Open: file://##; s#/index.html##')
echo "html in openable (expect present):"; find "$O5" -name 'transcript.html'

uat_reset
echo '{ "includeRenderedTranscript": false }' > .eval-pack.json
/eval-pack:generate 2>&1 | tee /tmp/g6.log
O6=$(grep -oE 'Open: file://\S+/index.html' /tmp/g6.log | sed -E 's#Open: file://##; s#/index.html##')
echo "html in openable (expect none):"; find "$O6" -name 'transcript.html'
```
Expected: with `includeRenderedTranscript` at its default (`true`), `transcript.html` is
**present**. With `includeRenderedTranscript: false`, `transcript.html` is **absent**.

**Pass/Fail:** PASS iff (a) empty rules leave transcripts unaltered, (b) `includeRawTranscript`
defaults to excluding raw jsonl and `true` bundles it, AND (c) `includeRenderedTranscript`
defaults to bundling `transcript.html` and `false` drops it.

---

## 6. Prompt / Rubric / Stance (P1)

### SC-PRS-01 — Each stance changes evaluator tone (objective + documented-subjective)

**Setup:** `uat_reset`. For each of `skeptical-reviewer`, `collaborative-coach`, `compliance-auditor`, set `{ "analysisStance": "<name>" }` and run `/eval-pack:generate` on the **same** conversation. Keep the three `analysis.json` outputs.

**Steps — objective checks (the real pass criteria):**
```bash
# 1) resolved stance text equals the preset file, byte for byte, per stance:
for s in skeptical-reviewer collaborative-coach compliance-auditor; do
  uat_reset; printf '{ "analysisStance": "%s" }' "$s" > .eval-pack.json
  python3 ~/Code/eval-pack/scripts/resolve_config.py "$(pwd)" /tmp/uat-pack >/dev/null
  python3 - "$s" <<'PY'
import json,sys
s=sys.argv[1]
c=json.load(open("/tmp/uat-pack/eval-config.json"))
preset=open(f"/Users/jasonsmith/Code/eval-pack/presets/stances/{s}.md").read()
assert c["analysisStanceText"]==preset, f"{s}: stanceText != preset file"
print(s,"stanceText==preset OK")
PY
done
# 2) the three analysis.json outputs are NOT identical (the differing prompt must move the output):
md5 -q analysis_skeptical.json analysis_coach.json analysis_auditor.json | sort -u | wc -l
# expect 3 distinct hashes  (save each analysis.json under those names as you run them)
```
**Steps — documented-subjective check:** For each stance, record in the results table whether the analysis prose exhibits the stance's characteristic framing (skeptical → risk/challenge language; coach → encouragement/next-steps; auditor → compliance/evidence language). This is a human judgment, logged as evidence, not the gating criterion.

**Expected:** objective (1) `analysisStanceText` equals the preset file for all three; objective (2) three distinct `analysis.json` hashes. Unknown stance halts (SC-NEG-06).
**Pass/Fail:** PASS iff both objective checks hold (stanceText==preset for each, and the three analyses differ). The subjective tone read is recorded but does not by itself fail the scenario.

### SC-PRS-02 — rubric / retrospectiveQuestions / evaluatorPromptFile consumed (objective)

**Setup:** `uat_reset`. Set a non-empty `rubric` (band→criteria) with a distinctive marker phrase (e.g. a criterion string `RUBRIC-MARKER-BETA`), custom `retrospectiveQuestions` including a unique sentinel question (e.g. `"What is the SENTINEL-Q7 risk?"`), and an `evaluatorPromptFile` whose contents include a sentinel token `PROMPTFILE-MARKER-9`.

**Steps — objective:**
```bash
python3 ~/Code/eval-pack/scripts/resolve_config.py "$(pwd)" /tmp/uat-pack >/dev/null
# a) the resolver-assembled prompt inputs carry the custom strings verbatim:
grep -o 'RUBRIC-MARKER-BETA\|SENTINEL-Q7\|PROMPTFILE-MARKER-9' /tmp/uat-pack/eval-config.json | sort -u
# expect all three markers present
/eval-pack:generate 2>&1 | tee /tmp/uat-gen.log
OPENDIR=$(grep -oE 'Open: file://\S+/index.html' /tmp/uat-gen.log | sed -E 's#Open: file://##; s#/index.html##')
# b) the produced analysis exposes the rubric target fields:
python3 - <<PY
import json
a=json.load(open("$OPENDIR/analysis.json"))
for f in ["confidencePercent"]:
    assert f in a.get("highlights",a), f"missing {f}"
for f in ["businessRisk","repoImprovements","userImprovements"]:
    assert f in a, f"missing {f}"
print("rubric target fields present")
PY
# c) the sentinel retrospective question is addressed in the output:
grep -oiI 'SENTINEL-Q7' "$OPENDIR/analysis.json" && echo "sentinel Q consumed" || echo "!! sentinel Q not reflected"
```
**Expected:** (a) all three markers appear in the assembled `eval-config.json` prompt inputs (objective proof the fields are wired into the evaluator prompt); (b) rubric target fields (`confidencePercent`, `businessRisk.level`, `repoImprovements`, `userImprovements`) exist in `analysis.json`; (c) the sentinel question appears in the analysis output (objective proof the custom question steered the evaluator). The overall "quality" of steering remains a recorded human note.
**Pass/Fail:** PASS iff (a) and (b) hold AND (c) shows the sentinel reflected in the output. Missing marker in the assembled prompt, or missing rubric field, = FAIL.

### SC-PRS-03 — detect_patterns / extract_tools honor thresholds — all three knobs (P1)

**Goal:** `scopeDriftFileThreshold`, `retryAmberThreshold`, and `skillArgsMaxLen` genuinely flow through. Each knob gets its own step.

**Setup:** `uat_reset`; a conversation containing ≥1 retry, a scope touching several files, and at least one Skill invocation with a long args string (> the value you will set).

**Steps:**
```bash
# (a) retryAmberThreshold: default 4 → no amber; set 1 → amber appears
uat_reset; echo '{ "retryAmberThreshold": 1 }' > .eval-pack.json
/eval-pack:generate 2>&1 | tee /tmp/g.log
O=$(grep -oE 'Open: file://\S+/index.html' /tmp/g.log | sed -E 's#Open: file://##; s#/index.html##')
python3 -c 'import json;p=json.load(open("'$O'/patterns.json"));print("amber:",any("amber" in json.dumps(x).lower() for x in (p if isinstance(p,list) else p.values())))'

# (b) scopeDriftFileThreshold: lower it and confirm the scope-drift flag flips on
uat_reset; echo '{ "scopeDriftFileThreshold": 1 }' > .eval-pack.json
/eval-pack:generate 2>&1 | tee /tmp/g.log
O=$(grep -oE 'Open: file://\S+/index.html' /tmp/g.log | sed -E 's#Open: file://##; s#/index.html##')
grep -oiI 'scope.?drift' "$O/patterns.json" | head

# (c) skillArgsMaxLen: set small and confirm tools.json truncates the args
uat_reset; echo '{ "skillArgsMaxLen": 12 }' > .eval-pack.json
/eval-pack:generate 2>&1 | tee /tmp/g.log
O=$(grep -oE 'Open: file://\S+/index.html' /tmp/g.log | sed -E 's#Open: file://##; s#/index.html##')
python3 - <<PY
import json
t=json.load(open("$O/tools.json"))
tools=t.get("tools",t if isinstance(t,list) else [])
longest=max((len(str(x.get("args",""))) for x in tools), default=0)
print("longest args len:",longest)
assert longest<=12, f"args not truncated to skillArgsMaxLen=12 (got {longest})"
print("skillArgsMaxLen truncation OK")
PY
```
**Expected:** (a) amber retry flag present at threshold 1 where it was absent at the default of 4; (b) scope-drift flag present after lowering; (c) every captured skill-args string in `tools.json` is ≤ 12 chars (truncated).
**Pass/Fail:** PASS iff all three knobs flip/enforce their behavior. Any knob with no observable effect = FAIL.

### SC-PRS-04 — analysis disabled + lenses configured (P1) ⚠️ anchors skills-agent MEDIUM

**Goal:** With the analysis option **false** and a non-empty `analysisLenses`, the lens/aggregation step must not blow up on the missing `highlights.confidencePercent` (the disabled path writes only `{title, disabled}`).
**Setup:** `uat_reset`; run generate with analysis disabled AND `{ "analysisLenses": [{"skill":"some-skill","role":"scorer"}], "verdictAggregation":"min" }`.
**Expected:** the lens step **skips cleanly or degrades to a noted failure** — it must not error on an undefined CORE. Run completes; `$ZIP` produced; Step 4 (lenses) does not crash.
**Pass/Fail:** PASS iff the run completes and Step 4 does not crash on missing `confidencePercent`. A traceback = FAIL (Silent-assumption defect at `skills/generate/SKILL.md` Step 4).

> Note: pre-2026-07-23 this scenario referenced "Step 4.7" — the lens-decomposition pipeline
> reorder (lenses now run BEFORE the evaluator, so its "read lenses" instruction is fulfillable)
> renumbered lens dispatch to Step 4 and the evaluator to Step 4.5. Same behavior, new numbers.

### SC-PRS-05 — Deferred keys have no false effect (P2)

**Goal:** `testCommands` and `ticketPattern` are detected/written by setup but not yet consumed.
**Setup:** `uat_reset`; `testCommands: ["echo NEVER_RUN"]`, `ticketPattern: "UAT-\\d+"`.
**Steps:** run generate; confirm the test step does **not** execute `echo NEVER_RUN` (grep generate output for `NEVER_RUN` → absent), and `ticketPattern` produces no observable linkification/behavior this release.
**Pass/Fail:** PASS iff setting these does not change behavior yet (prevents a false expectation). Note the expectation gap for docs.

---

## 7. Lenses + Aggregation + Guards (P1/P2)

### SC-LEN-01 — Lenses tab renders REAL content, not `[object Object]` (P1) ⚠️ anchors lenses & template HIGH

**Goal:** The transparency/attribution panel must be human-readable in the **real** rendered report — not merely in an isolated JS repro.

**Setup:** `uat_reset`. Configure at least one contributor and one scorer lens:
```json
{ "analysisLenses": [
    {"skill":"security-review","role":"contributor"},
    {"skill":"perf-scorer","role":"scorer"} ],
  "verdictAggregation":"min" }
```
Run `/eval-pack:generate`, capture `$OPENDIR` (0.7), open `$OPENDIR/index.html`, click the **Lenses** tab.

**Steps / checks (drive the REAL renderLenses, not a toy):**
- In the browser, the aggregation line reads e.g. `core 82  min lenses -> final 60` with **real numbers**.
- Each card shows a real **skill name**, **score/rationale** (scorer), **title/findings** (contributor), and a readable **error** (failure).
- Objective grep of the shipped artifact for the failure signature:
```bash
grep -c '\[object Object\]' "$OPENDIR/index.html"    # must be 0
```
- Optional headless confirmation without eyeballing (drives the actual `renderLenses` over real data):
```bash
node -e '
const fs=require("fs");
const html=fs.readFileSync(process.argv[1],"utf8");
if(/\[object Object\]/.test(html)){console.error("FAIL: [object Object] in rendered report");process.exit(1)}
console.log("no [object Object] in index.html")' "$OPENDIR/index.html"
```

**Known risk (audit — likely FAIL):** `renderLenses` (`templates/html/scripts.js`) uses `safe()` inside **plain** template literals instead of the `html\`\`` tag, so every dynamic value stringifies to `[object Object]`. The isolated repro `node -e 'const safe=x=>({});console.log(\`score: ${safe(60)}\`)'` demonstrates the quirk but does **not** prove the real panel; the authoritative check is `grep -c '[object Object]' "$OPENDIR/index.html"` == 0 and the visual card inspection. If any field in the panel reads `[object Object]`, this is a **FAIL** filed against `templates/html/scripts.js:renderLenses` (fix: use `html\`\`` or `escapeHtml()`).
**Pass/Fail:** PASS iff the shipped `index.html` contains zero `[object Object]` occurrences AND every lens card shows real content. Any `[object Object]` = FAIL (P1).

### SC-LEN-02 — Scorer failure must not silently fail-open under `min` (P2) ⚠️ anchors lenses MEDIUM

**Goal:** A gating scorer that crashes must not silently let the verdict pass.
**Setup:** `uat_reset`; configure a scorer lens whose skill **errors out mid-run**, with `verdictAggregation:"min"`.
**Steps:** generate; capture `$OPENDIR`; inspect `lenses.json` `failures[]` and the computed `finalScore`.
**Expected/Known:** Because a failed scorer is dropped from the scores list, under `min` its removal can only **raise** the final score — a crash neutralizes the gate. Confirm the failure is at least **visibly reflected** (a readable failure card, per SC-LEN-01) and `lenses.json.failures[]` names the failed skill.
**Pass/Fail:** PASS iff the failure is visibly recorded (card + `failures[]` entry) AND product accepts that a crashed scorer does not gate; otherwise file as fail-open defect.

### SC-LEN-03 — finalScore is informational only (P2) ⚠️ anchors lenses LOW

**Goal:** Ensure testers know the **headline** verdict is core-only.
**Setup:** `uat_reset`; a scorer lens + `min` that lowers `finalScore`.
**Steps:** check whether the top-of-report confidence/verdict changes or only the Lenses-panel line moves.
**Expected/Known:** Only the Lenses line moves; the headline (`highlights.confidencePercent`) is unchanged (scorers cannot corrupt the core verdict — integrity holds, but the "scorers influence the verdict" capability is currently cosmetic).
**Pass/Fail:** Behavioral PASS iff observed matches; record the Paper-Tiger gap (advertised gating is cosmetic) for product.

### SC-LEN-04 — Aggregation math & unknown rule (P1)

**Setup:** `uat_reset`.
**Steps:** Set `verdictAggregation` to `core`, `min`, `mean` in turn; for each, confirm `lenses.json` `finalScore` matches `aggregate.aggregate` on the same score list:
```bash
python3 - <<PY
import sys;sys.path.insert(0,"/Users/jasonsmith/Code/eval-pack/scripts")
import aggregate,json
L=json.load(open("$OPENDIR/lenses.json"))
scores=[s["score"] for s in L.get("scores",[])]; core=L.get("core")
for rule in ("core","min","mean"):
    print(rule, aggregate.aggregate(core, scores, rule))
PY
```
Unknown rule halts at resolve (SC-NEG-08).
**Pass/Fail:** PASS iff `finalScore` matches the rule's computed value for each of the three, and an unknown rule halts.

### SC-LEN-05 — Zero-lens run (Airplane Test) (P1)

**Setup:** `uat_reset`; `analysisLenses: []`.
**Steps:** generate; open report.
**Expected:** normal report, **no Lenses tab**, unchanged core verdict; `lenses.json` may be absent (renders cleanly as `{}`); no crash.
**Pass/Fail:** PASS iff no tab, no crash, verdict unchanged.

### SC-LEN-06 — Lens RUNS but returns malformed output (P1)

**Goal:** Distinct from SC-LEN-02 (scorer crashes) and SC-NEG-10/11 (bad lens **config** shape). Here the lens executes and returns a **runtime** value that `aggregate.aggregate()` never validates: non-numeric score, out-of-range (`9999`, `-5`), missing `score` field, or non-JSON blob.

**Setup:** `uat_reset`; configure a scorer lens whose skill emits, across separate runs, each malformed shape below (use a stub skill or a lens pointed at a skill you can make return canned output):
- `{"score": "high"}` (non-numeric)
- `{"score": 9999}` and `{"score": -5}` (out of range)
- `{}` (missing score)
- `not json at all` (non-JSON)

**Steps:** for each, run generate with `verdictAggregation:"min"` and `"mean"`; capture `$OPENDIR`; inspect:
```bash
python3 -c 'import json;L=json.load(open("'"$OPENDIR"'/lenses.json"));print("finalScore=",L.get("finalScore"),"failures=",L.get("failures"))'
grep -c '\[object Object\]\|NaN\|null' "$OPENDIR/index.html"
```
**Expected (intended):** each malformed return is either (a) rejected and recorded as a **failure** (dropped from scoring, visible failure card, `failures[]` entry), or (b) clamped/validated to a sane number with a recorded warning. What is NOT acceptable: `aggregate` crashing (traceback, lost zip), or a garbage `finalScore` (`NaN`, `9999`, `-5`, a string) silently shipped as the panel number.
**Known risk:** `aggregate.aggregate()` does no numeric/range validation → `min`/`mean` may crash on a string or emit garbage. If so, file against `scripts/aggregate.py` (missing input validation) and `skills/generate/SKILL.md` lens step (no schema check on lens output).
**Pass/Fail:** PASS iff every malformed lens return is quarantined as a visible failure or safely clamped, with no crash and no garbage `finalScore`. Any traceback, `NaN`, or out-of-range number in the shipped panel = FAIL (P1).

### SC-LEN-07 — Lens references an uninstalled / unresolvable skill (P1)

**Goal:** How generate degrades when a lens names a skill that **cannot be resolved at run time** (never installed) — distinct from a skill that installs and then errors (SC-LEN-02).

**Setup:** `uat_reset`; `{ "analysisLenses": [{"skill":"does-not-exist-skill-xyz","role":"scorer"}], "verdictAggregation":"min" }`.
**Steps:** generate; capture `$OPENDIR`; inspect exit/output and `lenses.json`.
**Expected:** generate completes and ships the zip; the unresolvable lens is recorded as a **failure** (visible card + `failures[]` naming `does-not-exist-skill-xyz`), and the core verdict is unaffected. NOT acceptable: a hard crash, a silent drop with no failure record, or the whole run aborting.
**Pass/Fail:** PASS iff the run completes, the missing skill is visibly recorded as a failure, and no crash. A silent no-op (lens vanishes with no signal) = FAIL (Silent Fallback).

---

## 8. Cosmetics / Template (P1/P2)

### SC-TPL-01 — Custom branding & subjectNoun (P1)

**Setup:** `uat_reset`; `{ "brandName":"Acme Review", "footerText":"© Acme", "reportTitle":"Acme Report", "subjectNoun":"service" }`.
**Steps:** generate; capture `$OPENDIR`; confirm logo=`Acme Review`, footer=`© Acme`, browser tab title=`Acme Report`, and headings say **service**. Then check completeness of the noun swap:
```bash
grep -c '\bextension\b' "$OPENDIR/index.html"   # record remaining occurrences
grep -c '\bservice\b'   "$OPENDIR/index.html"
```
**Expected/Known:** branding strings are injected via `textContent` (not HTML-parsed) so they cannot break markup. `subjectNoun` replaces only the **first** `\bextension\b` in three-column headings — so residual "extension" occurrences may remain. Record the exact count; any user-facing heading still reading "extension" where "service" was expected is a **P2 inconsistency defect**.
**Pass/Fail:** PASS iff logo/footer/title/heading branding applies; log every missed "extension" occurrence with its location.

### SC-TPL-02 — Section toggle/order & all-unknown list (P1/P2)

**Setup:** `uat_reset`.
**Steps:**
- `{ "sections": ["tools","summary","tests"] }` → capture `$OPENDIR`; confirm only those tabs, in that order, first tab (`tools`) active:
```bash
grep -oE 'data-tab="[^"]+"' "$OPENDIR/index.html"
```
- `{ "sections": ["typoTab","alsoWrong"] }` → confirm the nav does not become **completely empty** with a visible-but-unreachable panel.
**Expected/Known:** unknown names are skipped; an all-unknown list hides every tab button and leaves `first` undefined so nav is unusable while the summary panel stays visible (silent degrade, no crash). Record whether an empty nav is acceptable or should fall back to defaults (P2).
**Pass/Fail:** PASS iff valid lists reorder correctly (button order matches config, first active); flag the empty-nav edge for product.

### SC-TPL-03 — Theme selection & localStorage precedence (P1) + URL-template hardening (P2)

**Theme (P1):** `uat_reset` between each.
```bash
# Preconditions for each case: clear the saved theme unless the case sets it.
# In the browser devtools console for the opened index.html:
#   localStorage.removeItem('eval-pack-theme')   // clear
#   localStorage.setItem('eval-pack-theme','light')  // set (case d)
```
- (a) no config → dark.
- (b) `defaultTheme:"light"` (localStorage cleared) → forces light.
- (c) `defaultTheme:"system"` (localStorage cleared) → follows OS `prefers-color-scheme` (toggle OS appearance to confirm both directions).
- (d) `defaultTheme:"dark"` **but** `localStorage['eval-pack-theme']='light'` → **light wins** (a saved user choice overrides config). Reload with the key set; confirm the applied `data-theme`.
Precedence rule under test: **saved localStorage theme > config `defaultTheme` > built-in dark default.** Verify each by reading the effective `document.documentElement.dataset.theme` (or the applied CSS) after load.

**URL templates (P2, security hardening):** `uat_reset`; a `repoBaseUrl` with a `javascript:`/`data:` scheme.
```bash
grep -oE 'href="[^"]*"' "$OPENDIR/index.html" | grep -i 'javascript:\|data:' && echo ">>> LIVE DANGEROUS SCHEME <<<"
```
**Expected/Known:** hrefs are escaped against attribute breakout but the **scheme is not validated** — a `javascript:` value may yield a clickable script URL. If a live `javascript:`/`data:` href appears, file as a hardening defect (author-controlled config, low severity).
**Pass/Fail:** Theme PASS iff all four cases (a–d) apply the expected theme AND the localStorage-over-config precedence in (d) holds. URL PASS iff dangerous schemes are rendered inert OR the risk is explicitly accepted and logged.

### SC-TPL-04 — path linkification (P1)

> Note (2026-07-23): this scenario previously also covered `commitUrlTemplate` (commit-cell
> linkification). That key was removed end-to-end (lens-decomposition Task 7) — its only renderer
> consumer was removed in Task 1, leaving it a passthrough fossil with no template reader. Scenario
> narrowed to the surviving `repoBaseUrl` behavior.

**Setup:** `uat_reset`.
**Steps:** With `repoBaseUrl` set, diff file paths become repo-relative links; without it they render as plain code (baseline). Confirm resolved hrefs point at the expected path.
**Pass/Fail:** PASS iff links appear only when configured and resolve correctly.

### SC-TPL-05 — Section list edge already covered; theme covered — reserved. (No-op placeholder to preserve numbering.)

### SC-TPL-06 — zipNameTemplate: custom filename, `$`-substitution, path traversal (P2)

**Goal:** The shipped-zip filename customization is otherwise untested. Cover the happy path, template-variable substitution surprises, and a path-traversal attempt.

**Setup/Steps — `uat_reset` before each:**

(a) **Happy path:** `{ "zipNameTemplate": "acme-{branch}-report" }` (or whatever token the schema documents — substitute the real placeholder name).
```bash
/eval-pack:generate 2>&1 | tee /tmp/g.log
grep -oE 'Eval pack rendered to \S+' /tmp/g.log
```
Expected: zip filename reflects the template with the placeholder resolved (e.g. `acme-<branch>-report.zip`), written **inside** the output dir.

(b) **`$`-substitution surprise:** `{ "zipNameTemplate": "rep$&ort-{branch}" }` and `{ "zipNameTemplate": "rep\\1ort" }`.
Expected: literal `$&`/`\1` do not trigger regex-replacement backref expansion in the final name; the filename is either the literal string or a documented-sanitized form. A mangled/duplicated name from `String.replace` backref semantics = defect.

(c) **Path traversal:** `{ "zipNameTemplate": "../../evil" }` and `{ "zipNameTemplate": "/tmp/uat-escape/evil" }`.
```bash
/eval-pack:generate 2>&1 | tee /tmp/g.log
grep -oE 'Eval pack rendered to \S+' /tmp/g.log
ls -la /tmp/uat-escape 2>/dev/null && echo ">>> ZIP ESCAPED OUTPUT DIR <<<"
```
Expected: the template must **not** write the zip outside the intended output dir. The tool either sanitizes path separators (slug) — confirm the zip lands in the output dir with a flattened name — or rejects the template with an actionable message. A zip written to `../../` or `/tmp/uat-escape` = hardening defect (author-controlled config, low–medium severity).

**Pass/Fail:** PASS iff (a) applies the template, (b) treats `$`/backref sequences literally (no mangling), and (c) confines the zip to the output dir (no traversal escape). Log any escape or mangling.

### SC-TPL-07 — `messages` override changes displayed report strings (P2)

**Goal:** SC-CFG-08 only proves the merged `messages` **dict shape**; this proves a `messages` override actually **changes a rendered string**.

**Setup:** `uat_reset`. Set a `messages` entry that maps a known report string key to a sentinel value, e.g. `{ "messages": { "<known-key>": "ACME-CUSTOM-STRING-42" } }` (use a real key from the default `messages` map — inspect `templates/html` or the default config for a valid key).
**Steps:** generate; capture `$OPENDIR`; grep the report:
```bash
grep -c 'ACME-CUSTOM-STRING-42' "$OPENDIR/index.html"    # expect >= 1
```
**Expected:** the sentinel appears in the rendered report where the default string would otherwise be, proving `messages` is consumed for display (not merely stored).
**Pass/Fail:** PASS iff the sentinel string appears in the rendered output. Absent = FAIL (Paper Tiger: `messages` accepted but not consumed).

---

## 9. Setup Wizard (P1)

### SC-SET-01 — Express setup on varied repos, with expected key set

**Setup:** `uat_reset`. Run `/eval-pack:setup` on each of: an npm repo (`package.json` with `scripts.test`), a `pyproject.toml` repo, a `Makefile` repo, a monorepo (multiple `package.json`), and a repo with `.github/PULL_REQUEST_TEMPLATE.md`.
**Steps:** For each, inspect the written `.eval-pack.json` and let Step 5 run `resolve_config.py "$(pwd)" --check`. **Enumerate the expected keys per repo type** so the scenario fails on too-few or wrong values, not just on validity:

| Repo type | Keys the wizard SHOULD write (verify present + plausible value) | Keys that must NOT appear |
|---|---|---|
| npm w/ `scripts.test` | `testCommands` (contains the npm test invocation), `$schema` | any unknown key |
| `pyproject.toml` | `testCommands` (pytest/py runner), `$schema` | `languages`, `monorepo` |
| `Makefile` | `testCommands` (make target), `$schema` | unknown keys |
| monorepo | `$schema`; testCommands if detectable | `monorepo`, `languages` (no such schema key) |
| PR-template repo | `$schema`; `ticketPattern` only if a pattern is inferable | `prTemplate`, unknown keys |

```bash
# per repo:
python3 - <<'PY'
import json
c=json.load(open(".eval-pack.json"))
print("keys:",sorted(c))
PY
python3 ~/Code/eval-pack/scripts/resolve_config.py "$(pwd)" --check ; echo "exit=$?"
```
**Expected:** the file contains **only schema-valid keys**, includes the expected keys for that repo type with plausible values, omits every "must NOT appear" key, and Step 5 prints `config valid` (exit 0).
**Pass/Fail:** PASS iff, per repo type, the written key set matches the table (all expected keys present, no forbidden keys) AND `--check` passes. Missing an expected detected key, or a wrong value, = FAIL (not merely "it validated").

### SC-SET-02 — Detected concepts with no config landing spot (P2) ⚠️ anchors skills-agent LOW

**Goal:** Step 1 probes `languages`, `monorepo`, and PR-template — but there are **no** such config keys and the schema is `additionalProperties:false`.
**Setup:** `uat_reset`; run setup on a monorepo / multi-language repo.
**Steps:** Confirm the wizard does **not** write a `languages`/`monorepo` key (which would make Step 5 `--check` fail with `unknown config key`). These detections must surface only as report/prose, never as an unsupported key.
**Pass/Fail:** PASS iff `.eval-pack.json` validates and no dead/unsupported key is written. An `unknown config key` at Step 5 = FAIL.

### SC-SET-03 — Bad key at setup halts (P0)

**Setup:** `uat_reset`.
**Steps:** Hand-add an unknown key to `.eval-pack.json`, run `/eval-pack:setup`; Step 5 `--check` must report the error and NOT claim success. (Overlaps SC-NEG-12.)
**Pass/Fail:** PASS iff setup halts with the stderr error.

### SC-SET-04 — Schema enum & type coherence with runtime (P2)

**Goal:** Prove editor-side JSON-Schema validation and runtime `validate()` agree — enums AND the full key set.
**Steps:**
```bash
python3 - <<'PY'
import json,sys
sys.path.insert(0,"/Users/jasonsmith/Code/eval-pack/scripts")
import config
schema=json.load(open("/Users/jasonsmith/Code/eval-pack/schema/eval-pack.schema.json"))
props=schema.get("properties",{})
runtime=set(config._TYPES) if hasattr(config,"_TYPES") else set()
# a) $id vs $schema-URL coherence handled in SC-SET-06
# b) every runtime key exists in schema with matching type family:
missing=[k for k in runtime if k not in props]
print("runtime keys missing from schema:",missing)
# c) additionalProperties false:
print("additionalProperties:",schema.get("additionalProperties"))
# d) enum sources in sync:
import aggregate
print("aggregation enum schema:",props.get("verdictAggregation",{}).get("enum"))
print("aggregation runtime:",getattr(aggregate,"AGGREGATION_RULES",None) or getattr(config,"AGGREGATION_RULES",None))
print("theme enum schema:",props.get("defaultTheme",{}).get("enum"))
print("theme runtime:",getattr(config,"THEMES",None))
PY
```
**Expected:** `runtime keys missing from schema` is empty (every `_TYPES` key is declared in the schema so editors validate it); `additionalProperties` is `false`; the `verdictAggregation` and `defaultTheme` enum lists in the schema exactly equal the runtime `AGGREGATION_RULES`/`THEMES`; lens `role` enum matches runtime.
**Pass/Fail:** PASS iff no runtime key is missing from the schema, `additionalProperties:false`, and every enum source matches. Any drift = P2 defect (editors silently won't validate a key present in code but absent from schema).

### SC-SET-05 — Re-running setup is idempotent (P2)

**Goal:** The skill is "run once per repo," but re-runs are inevitable. A second run must not clobber manual edits, duplicate `.gitignore` entries, or corrupt config.
**Setup:** `uat_reset`; run `/eval-pack:setup` once. Then hand-edit `.eval-pack.json` to add a valid manual override (e.g. `"retryAmberThreshold": 2`) and add a comment/marker to `.gitignore` if applicable.
**Steps:** Run `/eval-pack:setup` **again**; then:
```bash
python3 -c 'import json;print(json.load(open(".eval-pack.json")).get("retryAmberThreshold"))'   # expect 2 preserved (or a clearly-communicated merge)
grep -c 'eval-pack' /tmp/uat-target/.gitignore   # expect no duplicate lines
git -C /tmp/uat-target diff --stat
```
**Expected:** the second run either (a) detects existing config and preserves the manual override (merging additively, communicating what it did), or (b) refuses to overwrite without explicit confirmation. `.gitignore` gains **no duplicate** eval-pack entries. `--check` still passes.
**Pass/Fail:** PASS iff the manual override survives (or the user is warned before any overwrite) AND `.gitignore` has no duplicated entries. Silent clobber of a manual edit, or duplicated gitignore lines, = FAIL.

### SC-SET-06 — `$schema` URL coherence AND resolvability (P2)

**Goal:** Editor autocomplete/validation silently no-ops if the `$schema` URL the wizard writes is unreachable or mismatched with the schema's `$id`.
**Steps:**
```bash
# a) string coherence: written $schema == schema $id
python3 - <<'PY'
import json
written=json.load(open(".eval-pack.json")).get("$schema")
sid=json.load(open("/Users/jasonsmith/Code/eval-pack/schema/eval-pack.schema.json")).get("$id")
print("written:",written); print("$id:",sid); print("match:",written==sid)
PY
# b) resolvability: is the URL actually published/reachable?
URL=$(python3 -c 'import json;print(json.load(open(".eval-pack.json")).get("$schema",""))')
curl -sSI --max-time 10 "$URL" | head -1
```
**Expected:** (a) the written `$schema` equals the schema `$id`; (b) the URL resolves (HTTP 200, or is a committed local/relative path that exists). If the URL 404s / is unpublished, editor validation silently no-ops — record as a P2 docs/release defect (either publish the schema or point `$schema` at a path that exists in-repo).
**Pass/Fail:** PASS iff `$schema`==`$id` AND the URL is reachable (or a valid in-repo path). A 404 / unreachable schema = P2 defect logged.

---

## 10. Platform, Interpreter & Robustness (P1)

### SC-ENV-01 — `python` vs `python3` and non-POSIX shells (P1)

**Goal:** The plan and skills invoke `python3` and bash. On Windows (and some minimal Linux images) only `python` is on PATH, and path separators differ. Confirm setup/generate resolve the interpreter portably and handle `extends` preset paths.
**Steps:**
- On a machine (or container) where **only `python`** is on PATH (no `python3` symlink), run `/eval-pack:setup` and `/eval-pack:generate`. Confirm the skill's script invocation finds the interpreter (via `python3` → `python` fallback or an explicit shim) rather than failing with `python3: command not found`.
- If a Windows environment is available, run setup/generate and confirm: (i) scripts execute, (ii) an `extends` preset path with `\`/`/` separators resolves, (iii) output paths in `Eval pack rendered to …` / `Open: …` are usable.
**Expected:** setup and generate complete on a `python`-only PATH and (where testable) on Windows; no `command not found`; preset paths resolve regardless of separator.
**Pass/Fail:** PASS iff both commands run to completion on a `python`-only environment (and Windows if available). A hard `python3: command not found` with no fallback = FAIL (portability defect). If Windows is unavailable, record as **untested** rather than PASS.

### SC-ENV-02 — No Python interpreter on PATH at all (P1)

**Goal:** If neither `python` nor `python3` is on PATH, setup/generate must surface an **actionable** error, not a cryptic failure or a silent skip (Black Box risk in the skill's script invocation).
**Steps:** In a shell with Python removed from PATH (e.g. `PATH=/usr/bin:/bin` on a box where python lives elsewhere, or a container without python), run `/eval-pack:setup` and `/eval-pack:generate`.
**Expected:** each stops with a clear message naming the missing interpreter ("python3/python not found — install Python 3.8+"), non-zero, and produces **no** partial pack.
**Pass/Fail:** PASS iff both fail loudly with an actionable message and write nothing. A silent skip, a produced-but-empty pack, or an opaque stack trace = FAIL (Black Box).

---

## 11. Cross-Layer / Integration Scenarios (P1)

### SC-INT-01 — extends preset + local override + env, end to end

**Setup:** `uat_reset`; `team-preset.json` + `.eval-pack.json` (extends it) + `.eval-pack.local.json` + one inline `CLAUDE_PLUGIN_OPTION_*`, spanning list, dict, scalar, and bool keys.
**Steps:** resolve; assert final values follow precedence (SC-CFG-01/01b) AND merge semantics (SC-CFG-02/08) simultaneously; then run a full `/eval-pack:generate` and confirm the report reflects the resolved values.
**Pass/Fail:** PASS iff the resolved config and the rendered report agree with the precedence+merge rules.

### SC-INT-02 — Full run: custom stance + redaction + one lens + custom branding

**Setup:** `uat_reset`, then:
```json
{
  "$schema": "https://github.com/smalls257/eval-pack/schema/eval-pack.schema.json",
  "analysisStance": "compliance-auditor",
  "redaction": ["AKIA-UAT-LEAK-[0-9A-Fa-fx]+"],
  "analysisLenses": [{"skill":"security-review","role":"contributor"}],
  "verdictAggregation": "core",
  "brandName": "Acme Review",
  "subjectNoun": "service",
  "publishOpenable": true
}
```
Plant `AKIA-UAT-LEAK-0xDEADBEEF` in the conversation.
**Steps:** `/eval-pack:generate`; capture `$ZIP`/`$OPENDIR` (0.7); verify **all** of:
1. Stance text = compliance-auditor preset (SC-PRS-01 objective check: `analysisStanceText`==preset file).
2. Secret absent from **every** artifact — run the **full SC-SEC-01 grep** over both `$OPENDIR` and the unzipped `$ZIP` (incl. `analysis.json`/`tools.json`/`data.json`/`index.html`), ending in `OVERALL: clean`. This inherits SC-SEC-01's explicit assertions, not an eyeball.
3. Lenses tab shows the real contributor card, `grep -c '[object Object]' "$OPENDIR/index.html"` == 0 (SC-LEN-01).
4. Branding: logo=`Acme Review`, headings say **service** (SC-TPL-01).
**Pass/Fail:** PASS iff all four hold (item 2 must show `OVERALL: clean` across `$OPENDIR` and the zip). This is the release-candidate acceptance run; any single failure blocks the layer it touches, and the secret leak blocks release outright.

### SC-INT-03 — Multi-session / multi-round merged pack (`merge_sessions.py`) (P1)

**Goal:** Config resolution and redaction across a **merged multi-session** transcript — including sessions whose source repos carry **different** configs — is entirely untested and is a real leak/precedence surface.
**Setup:** `uat_reset`. Produce two sessions to merge:
- Session A in a repo whose `.eval-pack.json` sets `{ "redaction": ["AKIA-UAT-LEAK-[0-9A-Fa-fx]+"], "brandName":"Acme A" }`; plant `AKIA-UAT-LEAK-0xDEADBEEF` in A's conversation.
- Session B in a repo with **no** redaction rule (or a different `brandName:"Acme B"`); plant the **same** token in B's conversation.
Then merge them (per the skill's multi-round flow / `scripts/merge_sessions.py`) into a single pack.
**Steps:** produce the merged pack; capture its `$ZIP`/`$OPENDIR`; then:
```bash
# a) redaction across the merged transcript — the token must be masked for BOTH sessions
#    if the merged pack's effective config includes the rule; if B's segment leaks, that is the finding:
grep -rnI "AKIA-UAT-LEAK" "$OPENDIR" && echo ">>> LEAK IN MERGED PACK <<<" || echo "merged clean"
# b) which config wins for the merged report (branding)?
grep -oE 'Acme A|Acme B' "$OPENDIR/index.html" | sort -u
```
**Expected:** the merged pack has a **defined, documented** config-resolution rule (e.g. the invoking repo's config governs the whole merged report). Under that rule:
- Redaction is applied consistently to the **entire** merged transcript — a secret must not survive in session B's segment just because B's own repo lacked the rule (if the governing config has the rule, everything is masked; if not, this must be a conscious, documented outcome). A token surviving anywhere in the merged pack when the governing config redacts it = **P0 leak**.
- Branding resolves to a single, predictable value (the governing repo's), not a nondeterministic mix.
**Pass/Fail:** PASS iff redaction is uniformly applied across all merged sessions per the governing config (no cross-session leak) AND config resolution for the merged pack is deterministic and documented. Any per-session leak, or nondeterministic/undocumented config precedence across sessions = FAIL (leak → P0; precedence ambiguity → P1).

---

## 12. Results Template (fill per scenario)

| ID | Priority | Result (PASS/FAIL/UNTESTED) | Evidence (command output / screenshot) | Defect ref |
|---|---|---|---|---|

**Release gate:** All **P0** (SC-BASE-01/02, SC-SEC-01/02a/03, all SC-NEG-01..14, SC-SET-03, SC-INT-02 items 1–2, SC-INT-03 no-leak) must PASS. A P0 FAIL blocks the release. P1 FAILs block their layer. P2 FAILs are triaged. Any P1 recorded UNTESTED (e.g. Windows leg of SC-ENV-01 with no Windows box) must be flagged in the release notes, not counted as PASS.

---

### Anchoring summary (each high/critical audit risk → catching scenario)

- config-core HIGH (extends silent no-op / case-wrong) → **SC-CFG-05**
- config-core HIGH (bool env garbage disables feature) → **SC-CFG-06**
- config-core MED (typo'd env key / dict-vs-list merge / stanceText round-trip / dict-key env coercion) → **SC-CFG-07/08/09, SC-NEG-13**
- config-core MED (empty-vs-absent file / nested-multi extends / negative thresholds / local-in-isolation) → **SC-CFG-11/12/13, SC-CFG-01b**
- fail-loud durability (stale artifact reuse) → **SC-NEG-14**
- security CRITICAL (derived artifacts un-redacted) → **SC-SEC-01**
- security HIGH (openableDir in-repo + edge cases) → **SC-SEC-02**
- security MED (regex bypass leftover jsonl / escape-vs-redact / bundling flag) → **SC-SEC-03/04/06**
- security (multi-session merged leak / precedence) → **SC-INT-03**
- lenses+template HIGH (`[object Object]`, driven over real render) → **SC-LEN-01 / SC-TPL-01**
- lenses MED/LOW (scorer fail-open / cosmetic finalScore / malformed lens output / uninstalled skill) → **SC-LEN-02/03/06/07**
- skills-agent MED (analysis-disabled + lenses crash) → **SC-PRS-04**
- skills-agent LOW (unsupported detected keys / re-run idempotency) → **SC-SET-02/05**
- template LOW (empty nav / `javascript:` URL / tab-title drift / zipNameTemplate traversal / messages consumed) → **SC-TPL-02/03/06/07 / SC-BASE-02**
- portability (python vs python3 / no interpreter) → **SC-ENV-01/02**
- schema/runtime coherence (key completeness / enum sync / $schema resolvability) → **SC-SET-04/06**

**Relevant source files** (branch `feat/config-foundation`, absolute paths): `/Users/jasonsmith/Code/eval-pack/scripts/config.py`, `/Users/jasonsmith/Code/eval-pack/scripts/resolve_config.py`, `/Users/jasonsmith/Code/eval-pack/scripts/render_html.py`, `/Users/jasonsmith/Code/eval-pack/scripts/redact.py`, `/Users/jasonsmith/Code/eval-pack/scripts/aggregate.py`, `/Users/jasonsmith/Code/eval-pack/scripts/merge_sessions.py`, `/Users/jasonsmith/Code/eval-pack/scripts/detect_patterns.py`, `/Users/jasonsmith/Code/eval-pack/scripts/extract_tools.py`, `/Users/jasonsmith/Code/eval-pack/templates/html/scripts.js`, `/Users/jasonsmith/Code/eval-pack/schema/eval-pack.schema.json`, `/Users/jasonsmith/Code/eval-pack/skills/setup/SKILL.md`, `/Users/jasonsmith/Code/eval-pack/skills/generate/SKILL.md`, `/Users/jasonsmith/Code/eval-pack/presets/stances/`.