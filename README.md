# eval-pack

A Claude Code plugin that generates eval packs — polished HTML reports capturing how AI-assisted code was produced. Designed for PR review workflows where reviewers need visibility into agent behavior, not just the diff.

## Screenshots

![Eval Pack — header, completion status, verdict, and session metrics](docs/screenshots/hero.png)

![Session metrics — per-model token breakdown and session stats](docs/screenshots/metrics.png)

![Tools tab — tool usage bar chart and subagents dispatched](docs/screenshots/tools.png)

## What's in an Eval Pack?

- **Verdict banner** — pass/fail based on agent-driven test results, plus a synthesized
  completion/confidence verdict informed by the judgment lenses below
- **Visual evidence** — screenshots from Playwright or browser verification
- **Session metrics** — per-model token breakdown (controller + subagents), turns, files changed
- **Session timeline** — human-readable narrative of what happened during the session
- **Heuristic flags** — false completions, retries, scope drift, test failures
- **Judgment lenses** — eight toggleable dimensions, each its own agent, each default-on:
  requirement-drift (did delivery match the ask?), verification-rigor (were claims backed by
  evidence?), review (adversarial findings), business-risk (stakeholder risk + mitigation),
  friction (dev-experience friction, classified), repo-improvements (how the codebase could
  improve), user-improvements (how well the developer owned the
  work — intent, engineering decisions, and the review/due-diligence the risk warranted, incl.
  when the *whether-to-check* decision itself was offloaded to the AI — vs. vibecoding; calls out
  both good ownership and offloaded-judgment moments, proportional to risk, each cited to a
  transcript moment, + an example better prompt, and an overall **Developer Ownership** level
  surfaced as an at-a-glance header card — high=good), and sycophancy (how much the assistant
  flattered/validated the developer vs. stayed candid — evidence-decoupled agreement, cited;
  grounded in the sycophancy literature).
  Every dimension is tunable per-repo via `analysisLenses` — see
  [Extension lenses](#extension-lenses--your-own-analyses-and-scores).
- **Tests tab** — deterministic, generated straight from `test-results.json`/`testCommands` exit
  codes, not LLM narrative. Note: this replaced the older LLM-authored `testsExisting` tab, which
  also called out coverage gaps (which areas were well-covered vs. not) — that narrative framing
  was dropped in the switch to deterministic facts; `verification-rigor`'s `unproven` array is the
  closest current equivalent for naming what wasn't demonstrated.
- **Tools tab** — tool usage bar chart, subagents dispatched with model tags, skills leveraged
- **Full transcript** — collapsible conversation history with syntax highlighting
- **Iteration rounds** — compare multiple runs side by side

## Requirements

- **Python 3** — required by the generation scripts (`extract_metrics.py`, `detect_patterns.py`, `extract_tools.py`, `render_html.py`); JSON parsing and zip packaging use the Python standard library, so no extra CLI tools are needed
- **gh** CLI — required by `/eval-pack:review` to create PRs and post comments

## Install

In Claude Code, run:

```
/plugin marketplace add smalls257/eval-pack
/plugin install eval-pack@eval-pack
```

Then run the setup skill to wire up the gitignore:

```
/eval-pack:setup
```

### Distribute to your team

To distribute the marketplace config to everyone who clones your repo, commit `.claude/settings.json` with:

```json
{
  "extraKnownMarketplaces": {
    "eval-pack": {
      "source": {
        "source": "github",
        "repo": "smalls257/eval-pack"
      }
    }
  }
}
```

Each dev still needs to run `/plugin marketplace add smalls257/eval-pack` and `/plugin install eval-pack@eval-pack` once to install the plugin.

## Usage

### Generate an eval pack

```
/eval-pack:generate
```

Produces a self-contained zip in `.eval-packs/<session-id>.zip`. Extract and open `index.html` in a browser.

### Generate + create PR

```
/eval-pack:review
```

Generates the eval pack, commits the zip to the current branch, and creates (or updates) a PR.

### Agent auto-generation

Agents can invoke `/eval-pack:generate` autonomously when they judge work is PR-ready. No hooks required — the agent calls the skill like any other.

## Configuration

eval-pack is configured per-repo via `.eval-pack.json` (committed) and `.eval-pack.local.json`
(gitignored, per-developer). Layering, lowest to highest: bundled defaults < `extends` presets <
`.eval-pack.json` < `.eval-pack.local.json` < `CLAUDE_PLUGIN_OPTION_*` env. Validation is
fail-loud: an unknown key, bad type, bad regex, or missing referenced file halts generation with
a precise error. Run `/eval-pack:setup` for a guided start. **Full per-key reference (every
option, type, default, and constraint):** [`docs/configuration.md`](docs/configuration.md).

```json
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
  "brandName": "Acme Eval", "subjectNoun": "service", "defaultTheme": "light",
  "templateDir": "eval-theme",
  "analysisLenses": [{"skill": "acme-security-lens", "role": "scorer"}],
  "verdictAggregation": "min"
}
```

Env values (`CLAUDE_PLUGIN_OPTION_<key>`) that start with `[` or `{` are parsed as JSON — the
only way to express a dict, or a list element containing a comma (a regex like `secret{1,3}`, for
example); `redaction` in particular REQUIRES the JSON form once a pattern has a comma. Any other
list value uses comma shorthand for simple tokens (`"a,b,c"`). File-layer lists (`.eval-pack.json`
/ `.eval-pack.local.json`) ADD to the defaults; start a list with `"!replace"` to replace them
instead (e.g. `["!replace", "ci-flake", "review-latency"]`) — a leading `"!replace"` in an env
JSON list is honored the same way.

Key groups below (full per-key reference: [`docs/configuration.md`](docs/configuration.md); types:
`schema/eval-pack.schema.json`):
- **Evaluation prompts** — `analysisStance` (bundled: skeptical-reviewer, collaborative-coach,
  compliance-auditor; or your own at `.eval-pack/stances/<name>.md`), `rubric` (band → criteria;
  the evaluator must name the band it applied, and a validator rejects unknown bands),
  `retrospectiveQuestions` (each must be answered — validated), `frictionCategories` (the
  taxonomy the `friction` lens's entries must draw from — validated), `evaluatorPromptFile` (extra
  grading guidance from a file in your repo). These gates are enforced by
  `scripts/validate_contracts.py`, not by prose: a violation halts the pipeline before render.
- **Heuristics** — `detectionPatterns` (a dict of regex lists — providing it replaces the WHOLE
  dict, so supply every group you want: done/correction/retry), `falseCompletionWindow`, `scopeDriftFileThreshold`,
  `retryAmberThreshold`, `flagSeverities` (retune or `"off"` any flag by id),
  `customDetectors` and `detectorScripts` (your own deterministic policy checks — see below).
- **Tests & tickets** — `testCommands` (run verbatim; real exit codes drive the verdict, enforced
  by a validator), `ticketPattern`, `ticketBaseUrl`.
- **Security** — `redaction` (regexes masked in every emitted artifact, keys and values, before
  escaping), `publishOpenable`, `openableDir`.
- **Report** — `brandName`, `reportTitle`, `footerText`, `subjectNoun`, `defaultTheme`,
  `sections`, `messages`, `templateDir` (project dir overriding index.html/styles.css/scripts.js
  per-file), `zipNameTemplate`, `repoBaseUrl`.
- **Pipeline** — `outputDir`, `analysis`, `includeRawTranscript` (bundle raw
  `transcript.jsonl`; default off), `includeRenderedTranscript` (render/bundle human-readable
  `transcript.html` + its Transcript artifact link; default on).

`pythonExecutable` stays a plugin option in `.claude/settings.json` (`pluginConfigs.eval-pack.options`)
rather than moving into `.eval-pack.json` — it has to resolve before any script, including the
config resolver itself, can run.

### Extension lenses — your own analyses and scores

A lens is YOUR agent that runs during evaluation. Declare it:

```json
{ "analysisLenses": [{ "skill": "acme-security-lens", "role": "scorer" }],
  "verdictAggregation": "min" }
```

and provide an agent by that name (e.g. `.claude/agents/acme-security-lens.md` in your repo). It
receives PACK_DIR / REPO_ROOT / DIFF_BASE and must write `PACK_DIR/lenses/acme-security-lens.json`:

- **scorer** (influences the verdict via `verdictAggregation`):
  `{"skill": "acme-security-lens", "role": "scorer", "score": 61, "rationale": "one sentence",
    "findings": [{"type": "issue", "detail": "..."}]}`
- **contributor** (adds an attributed report section, never touches the score):
  `{"skill": "...", "role": "contributor", "title": "Section title", "findings": ["...", "..."]}`

Guarantees, enforced by code: a configured lens that produces no output becomes a red
"Lens failed" flag (it cannot silently vanish); scorer scores are clamped to 0–100 and reach the
verdict banner and confidence card only through your declared aggregation rule; a failing lens
never crashes the eval. Bundled examples: `requirement-drift`, `verification-rigor`.

A lens may also carry a `version` (shown in the report, so results are only comparable within a
version); first-party lens versions come from the `agents/lenses/lens-versions.json` lockfile,
guarded by `tests/test_lens_versions.py`. See `docs/configuration.md` for details.

#### Custom rendering for a lens

By default a lens renders as a generic card (meta line, rationale, findings list). To control
how a specific lens's output looks in the report, point it at a repo-authored HTML template:

```json
{ "analysisLenses": [
    { "skill": "acme-security-lens", "role": "scorer", "template": ".eval-pack/templates/security.html" }
  ] }
```

The template is a small mustache-lite snippet rendered against your lens's own JSON output:

```html
<p>Risk score: <strong>{{score}}</strong></p>
<ul>
  {{#findings}}<li>{{.}}</li>{{/findings}}
</ul>
```

Supported syntax: `{{field}}` / `{{dot.path}}` (interpolates a value), `{{#arrayField}}...{{/arrayField}}`
(repeats the body once per array item, one level deep), and `{{.}}` inside a section (the item
itself, rendered the same readable way as the default findings list). Unknown fields render as
empty strings — a typo never crashes the report.

Security model: the template file is resolved and embedded at pack-build time from your repo
(same confinement as `evaluatorPromptFile`/`detectorScripts` — no `../` escapes, must exist) so
the **markup is trusted**. Every value it interpolates, however, is untrusted LLM output from the
lens's own JSON, and is **always HTML-escaped** — there is no way for a template to opt out of
escaping a value. If the template itself fails to render for a given record, that lens falls back
to a visible "template failed" card instead of a blank or broken one.

### Custom detectors — your own deterministic policy checks

No LLM involved: a detector is a regex policy (`customDetectors`) or your own script
(`detectorScripts`) run over the recorded session, feeding the same gated flags→verdict pipeline.

```json
{ "customDetectors": [
    { "id": "sudoUsed", "level": "red", "label": "sudo executed", "scope": "bash", "pattern": "\\bsudo\\b" },
    { "id": "envRead", "level": "amber", "label": ".env accessed", "scope": "files", "pattern": "\\.env$" }
  ],
  "detectorScripts": ["eval-detectors/compliance.py"] }
```

Scopes: `bash` (commands), `files` (paths), `text` (assistant), `user` (your prompts). A script
must print ONLY its JSON result on stdout — `{"flags": [{"id", "level", "label"}]}` — nothing
else; a stray debug `print()` before or after it makes the output unparsable and the whole run a
red "Detector script failed" flag. Scripts are run with the plugin's own Python interpreter
(`sys.executable`), so `detectorScripts` entries must be Python. Either way — malformed output or
a nonzero exit — becomes that same red flag; it can't vanish silently.

### Tuning your eval — the loop

1. Edit `.eval-pack.json` (rubric, stance, detectors, lenses, thresholds…).
2. Instant check: `python3 <plugin>/scripts/resolve_config.py . --check` — a bad key/regex/band
   halts here, not mid-run (or just run step 3; it validates first).
3. `/eval-pack:tune` — re-evaluates the latest pack with your new config in minutes: recorded
   facts (transcript, metrics, tests) are reused; only patterns, the evaluator, lenses, and the
   report re-run. Each tune appends a **round**, so the report shows your before/after.
   **Iterating on one lens? Re-run just that lens** — e.g. "tune only the sycophancy lens" (or
   `lens=sycophancy`). It re-dispatches that single lens against the prior round's on-disk outputs
   and reuses everything else — no regenerating the whole pack. Fast loop for lens-prompt tweaks.
4. Ship the config that produces the eval you trust; it's committed with the repo, so the whole
   team gets it.

## How It Works

1. Dev (or agent) runs `/eval-pack:generate`
2. Scripts extract metrics and detect heuristic patterns from the transcript
3. Claude runs appropriate tests, captures screenshots and logs
4. The configured judgment lenses run (default: requirement-drift, verification-rigor, review,
   business-risk, friction) — each an independent agent, each writing its own finding to
   `lenses/<skill>.json`
5. The evaluator synthesizes a single completion/confidence verdict from the lens findings and
   heuristic flags — it does not re-judge a dimension a lens already owns
6. HTML report is rendered with all data, zipped to `.eval-packs/<session-id>.zip`
7. `/eval-pack:review` commits the zip to the branch and creates a PR

### Lenses are default-on, and default-on means mandatory

All eight bundled lenses ship enabled in `analysisLenses` — that is the "preserve today's
behavior" baseline, not a suggestion. **Enabling a lens makes its execution mandatory**: once a
skill is listed in `analysisLenses`, a run where that lens produces no output is not a silent
gap — it surfaces as a non-suppressible red `lensFailed` flag. To turn a judgment dimension off,
remove its entry from `analysisLenses` (at any config layer); there is no "best effort" middle
ground where a configured lens is allowed to just not show up.
7. Reviewer downloads zip from the branch, extracts, opens `index.html`

## Output

`/eval-pack:generate` writes a portable `.zip` into your `outputDir` (default `.eval-packs/`)
**and** an uncompressed, openable copy into your system temp directory. The command prints an
`Open: file://…/index.html` path — open it directly in a browser, no unzip required. The zip is
what `/eval-pack:review` commits to a PR branch.

The analysis is written by an independent `eval-pack-evaluator` sub-agent, not by the agent that
did the work, so the evaluation is not self-graded. When the `analysis` option is `false`, the
pack renders an explicit "analysis disabled" banner instead of an AI evaluation.

## Ticket linking

`/eval-pack:review` adds a `## Ticket` reference to the PR body. It auto-detects a ticket key
matching `[A-Z][A-Z0-9]+-[0-9]+` (e.g. `PROJ-123`) from the branch name or this branch's commit
messages; if none is found it asks once (answer with a key, a full URL, or `none`). Set
`ticketBaseUrl` to render detected keys as clickable links. The reference is added when the PR is
first created.

## License

MIT
