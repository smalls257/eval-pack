# eval-pack configuration reference

Complete reference for every `.eval-pack.json` option. For a quick tour see the
[Configuration section of the README](../README.md#configuration); this document is the
exhaustive per-key list with types, defaults, and constraints.

The single source of truth in code is `scripts/config.py` (`DEFAULTS` + `validate()`) and
`schema/eval-pack.schema.json`. If this doc and those ever disagree, the code wins — file an issue.

---

## Where config lives

| File | Committed? | Purpose |
|------|-----------|---------|
| `.eval-pack.json` | yes | Team config for the repo. |
| `.eval-pack.local.json` | no (gitignore it) | Per-developer overrides. |
| `CLAUDE_PLUGIN_OPTION_*` env | n/a | Plugin-option layer (from `.claude/settings.json` `pluginConfigs`). |

Run **`/eval-pack:setup`** (or `/eval-pack-next:setup`) for a guided start that detects sane
defaults, asks only what it can't infer, writes `.eval-pack.json`, and validates it.

Add `"$schema": "./.eval-pack.schema.json"` at the top of your file for editor autocomplete.

## Layering (precedence, low → high)

```
bundled DEFAULTS  <  extends presets  <  .eval-pack.json  <  .eval-pack.local.json  <  CLAUDE_PLUGIN_OPTION_*
```

- **`extends`** — a preset (or list of presets) layered *under* your file, so your keys win over
  the preset's. Meta key; never part of the resolved config.
- **Validation is fail-loud.** An unknown key, wrong type, bad regex, unknown enum value, or a
  missing referenced file halts generation with a precise error — it never silently falls back to a
  default. (A leftover `includeTranscript` from before the raw/rendered split, for example, now
  errors as an unknown key rather than being ignored.)

### How lists and dicts merge

- **List keys** (e.g. `frictionCategories`, `redaction`, `testCommands`): a file-layer list **adds
  to** the lower layer. To replace instead, make `"!replace"` the **first** element:
  `["!replace", "ci-flake", "review-latency"]`. A literal `"!replace"` anywhere else in a resolved
  list is an error.
- **Dict keys** (e.g. `detectionPatterns`, `rubric`, `messages`, `flagSeverities`): a dict
  **replaces wholesale** — supply every entry you want. (So overriding `detectionPatterns` means
  providing all of `done`/`correction`/`retry`.)

### Env layer specifics

`CLAUDE_PLUGIN_OPTION_<key>` sets one key. A value starting with `[` or `{` is parsed as JSON — the
only way to express a dict, or a list element containing a comma (a regex like `secret{1,3}`). Any
other list value uses comma shorthand (`"a,b,c"`). `redaction` **requires** the JSON-array form once
a pattern contains a comma. Env values replace (they don't add).

`pythonExecutable` stays a plugin option in `.claude/settings.json`
(`pluginConfigs.eval-pack.options`), not in `.eval-pack.json` — it has to resolve before any script,
including the config resolver, can run.

---

## Key reference

Every key, its type, default, and constraints. All keys are optional; omitting one uses its default.

### Output & bundling

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `outputDir` | string | `".eval-packs"` | Directory for generated packs, relative to repo root. |
| `publishOpenable` | bool | `true` | Also write an unzipped, openable copy of the pack. |
| `openableDir` | string | `""` | Where the openable copy goes; empty = system temp. Refused if inside the repo (could be committed/pushed). |
| `includeRawTranscript` | bool | `false` | Bundle the raw machine-readable `transcript.jsonl` in the zip + openable copy. Off by default — the raw conversation is not shipped unless you opt in. |
| `includeRenderedTranscript` | bool | `true` | Render and bundle the human-readable `transcript.html` and its "Transcript" artifact link. Turn off to keep the conversation out of the bundle entirely; the report shows "Transcript excluded from this pack" instead of a dead link. |
| `zipNameTemplate` | string | `""` | Override the zip filename; empty = branch-derived name. |
| `analysis` | bool | `true` | Run the independent evaluator. `false` = heuristic flags only, with an "analysis disabled" banner (no fabricated score). |

> The two transcript flags are independent: `includeRawTranscript` controls the `.jsonl`,
> `includeRenderedTranscript` controls the `.html`. Default = rendered in, raw out.

### Evaluation (the grader)

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `analysisStance` | string | `"skeptical-reviewer"` | Named evaluator persona. Bundled: `skeptical-reviewer`, `collaborative-coach`, `compliance-auditor` (see `presets/stances/`). Or your own at `.eval-pack/stances/<name>.md`. |
| `evaluatorPromptFile` | string | `""` | Repo-relative file with extra grading guidance appended to the evaluator prompt. |
| `rubric` | dict | `{}` | `band → criteria` (criteria are strings). The evaluator must name the band it applied; a validator rejects an unknown band. Empty = built-in anchor. |
| `retrospectiveQuestions` | list | `[]` | Questions the evaluator must answer; each is enforced. Empty = built-in set. |
| `verdictAggregation` | string | `"core"` | How scorer-lens scores combine with the core verdict. One of `core` \| `min` \| `mean`. |

These are enforced by `scripts/validate_contracts.py` (a deterministic gate), not by prose — a
violation halts the pipeline before the report renders.

### Extension lenses

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `analysisLenses` | list of objects | the 8 bundled lenses | Each: `{ "skill": str, "role": "contributor"\|"scorer", "display"?: "card"\|"tab"\|"both", "template"?: str, "version"?: str, "model"?: "opus"\|"sonnet"\|"haiku"\|"fable" }`. |

- `role`: **scorer** returns a 0–100 `score` that reaches the verdict only through
  `verdictAggregation`; **contributor** adds an attributed report section and never touches the score.
- `display` (presentation): `tab` (default) = its own nav tab; `card` = a compact at-a-glance
  header card; `both` = a summary card up top **and** a detail tab. A `card` lens that produces
  detail (findings/mitigation/main-risk) still gets a tab so nothing is silently dropped.
- `template`: repo-relative HTML (mustache-lite) controlling how the lens renders. Markup is
  trusted (resolved from your repo, no `../` escape); every interpolated value is always HTML-escaped.
- `model` (cost/quality tuning): the model tier that runs THIS lens's subagent — `opus` | `sonnet` |
  `haiku` | `fable`. Omit to inherit the session model. Each lens reads the transcript, so on a large
  transcript the model choice is a big cost lever: keep judgment-heavy lenses (e.g. `sycophancy`,
  `user-improvements`, `review`) on `opus` and mechanical ones (`friction`, `requirement-drift`,
  `verification-rigor`) on `haiku`/`sonnet`. (Lens dispatch is skill-orchestrated, so the model is
  honored by the generate skill obeying the config — same trust level as the rest of lens dispatch.)

A configured lens that writes no output becomes a red "Lens failed" flag (it can't silently vanish);
a failing lens never crashes the eval. Default lenses:
`review`, `business-risk`, `friction`, `repo-improvements`, `user-improvements`, `sycophancy` (contributors),
`requirement-drift`, `verification-rigor` (scorers). See the README for the full lens authoring guide.
`sycophancy` is business-risk-shaped: a contributor emitting a low/medium/high level plus cited
findings (does not feed the verdict).

### Lens versioning

Every lens carries a `version`, shown in the report (meta line, failure cards, header cards) —
scores and findings are only comparable across runs that used the same version.

First-party lenses get their version from `agents/lenses/lens-versions.json`, a checked-in
lockfile that pairs each lens's `version` with the sha256 of its `.md` file. `tests/test_lens_versions.py`
recomputes those hashes and fails if a lens `.md` changed without a matching lockfile update — so a
rubric or scoring change cannot merge green without being versioned. To edit a lens `.md`, bump its
`version` and update its `sha256` in the lockfile in the same change. Bump the **major** version when
the change makes old and new scores non-comparable (e.g. a rubric or scoring change); minor/patch
bumps are for wording or clarity that don't affect comparability.

A `version` set directly on an `analysisLenses` config entry overrides the lockfile. Use this to pin
a first-party lens to a specific version, or to version a third-party lens whose `.md` doesn't live
under `agents/lenses/` and so has no lockfile entry.

### Heuristics, detectors & flags

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `detectionPatterns` | dict | English `done`/`correction`/`retry` regex lists | Regex lists that drive completion/correction/retry detection. Replaces the **whole** dict — supply all three groups. |
| `falseCompletionWindow` | int | `1` | How many entries after a completion claim to scan for a user correction. |
| `claimTruncLen` | int | `120` | Truncation length for quoted claim/response text in `patterns.json`. |
| `scopeDriftFileThreshold` | int | `10` | Files-changed above this raises a scope-drift amber flag. |
| `retryAmberThreshold` | int | `4` | Retries at/above this raises a high-retry amber flag. |
| `frictionCategories` | list | `["tooling","structure","naming","docs","other"]` | Taxonomy the `friction` lens's entries must draw from (validated). |
| `skillArgsMaxLen` | int | `200` | Truncation of skill args in `tools.json`. Must be ≥ 0. |
| `flagSeverities` | dict | `{}` | `flagId → "red"\|"amber"\|"green"\|"off"`. Retune or silence any built-in flag by id. |
| `customDetectors` | list of objects | `[]` | Declarative regex policy checks (no code exec). See below. |
| `detectorScripts` | list | `[]` | Repo-relative scripts run by `detect_patterns`, each printing `{"flags":[...]}`. Same trust class as `testCommands` — your repo's own code. |

**`customDetectors` object shape** — `{ "id": str, "level": "red"\|"amber"\|"green", "label": str,
"scope": "bash"\|"files"\|"text"\|"user", "pattern": regex, "threshold"?: int ≥ 1 (default 1) }`.
`id` must not collide with a built-in flag id and must be unique. `scope` selects what the regex
runs against (bash commands, changed file paths, assistant text, or user messages).

### Tests & tickets

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `testCommands` | list | `[]` | Commands run verbatim from repo root; their real exit codes drive the test verdict (enforced by a validator). Empty = auto-detect. |
| `ticketPattern` | string | `"[A-Z][A-Z0-9]+-[0-9]+"` | Regex the review skill matches to linkify ticket keys in PR bodies. |
| `ticketBaseUrl` | string | `""` | Prefix that turns a bare ticket key into a link (e.g. `https://YOURORG.atlassian.net/browse/`). Empty = plain text. |

### Security

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `redaction` | list of regex | `[]` | Patterns masked in **every** emitted artifact (keys and values) before HTML-escaping. Comma-unsafe: an env override must use the JSON-array form. |

### Report presentation

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `brandName` | string | `"Eval Pack"` | Report/logo brand. |
| `reportTitle` | string | `""` | Overrides the report title; empty = derived. |
| `footerText` | string | `""` | Footer text. |
| `subjectNoun` | string | `"extension"` | The noun the report uses for the thing evaluated (e.g. "service", "app"). |
| `defaultTheme` | string | `"dark"` | Initial theme. One of `dark` \| `light` \| `system`. |
| `sections` | list | `[]` | Explicit section order/visibility; empty = default order. |
| `messages` | dict | `{}` | Override individual UI strings. Replaces wholesale. |
| `repoBaseUrl` | string | `""` | Base URL for turning diff file paths into links. |
| `templateDir` | string | `""` | Repo dir overriding `index.html`/`styles.css`/`scripts.js` per-file (user file wins, bundled fills gaps). |

---

## Examples

### Minimal — real test commands + a redaction rule

```json
{
  "$schema": "./.eval-pack.schema.json",
  "testCommands": ["npm test", "npm run lint"],
  "redaction": ["sk-[A-Za-z0-9]+"]
}
```

### Keep the whole conversation out of shared bundles

```json
{
  "includeRawTranscript": false,
  "includeRenderedTranscript": false
}
```

The pack still contains metrics, analysis, lenses, and screenshots — just no conversation. (This is
also the privacy-safe posture for attaching a pack to a public PR.)

### A scoring lens that can veto the verdict, branded

```json
{
  "analysisLenses": [
    { "skill": "acme-security-lens", "role": "scorer", "display": "both",
      "template": ".eval-pack/templates/security.html" }
  ],
  "verdictAggregation": "min",
  "brandName": "Acme Eval", "subjectNoun": "service", "defaultTheme": "light"
}
```

### Retune heuristics + a custom detector

```json
{
  "retryAmberThreshold": 6,
  "flagSeverities": { "scopeDrift": "off" },
  "customDetectors": [
    { "id": "rawSqlInDiff", "level": "amber", "label": "Raw SQL in changed files",
      "scope": "files", "pattern": "(?i)\\bselect\\b.*\\bfrom\\b", "threshold": 1 }
  ]
}
```

---

## Applying changes without re-running the whole pipeline

After editing `.eval-pack.json`, **`/eval-pack:tune`** re-evaluates an existing pack with your new
config — it reuses the recorded facts (transcript, metrics, diffs) and re-runs only evaluation +
rendering, appending a new round. That's the fast loop for tuning rubric / stance / lenses /
detectors / branding. To iterate on a single lens's rubric/prompt, target it directly (e.g. "tune
only the sycophancy lens") — tune re-dispatches just that lens and reuses everything else on disk.
