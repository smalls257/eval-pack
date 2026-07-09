---
description: Bootstrap a repository to use eval-pack — a guided configuration wizard that detects sane defaults, asks only what it can't infer, writes .eval-pack.json, and validates it. Run once per repo.
tags: ["setup", "config", "wizard"]
---

# Setup Eval Pack — Guided Wizard

You are configuring eval-pack for this repository. Do not dump a form on the user: probe the
repo first, propose a justified draft, ask only what you genuinely cannot infer, then validate
what you wrote. Two modes:

- **Express** (default): probe, show the proposed config, confirm once, write.
- **Guided** (when the user passes `--guided`): walk each section with the user.

## Step 1: Probe — detect, don't interrogate

Inspect the repo BEFORE asking anything. Asking what is already on disk is friction. Gather:

- **testCommands** — from `package.json` `scripts.test`, `pyproject.toml`/`tox.ini`, a `Makefile`
  `test` target, or `Cargo.toml`. Record the actual command(s).
- **ticketPattern** — scan recent commit subjects (`git log --oneline -50`) for a ticket key
  shape (e.g. `ABC-123`). If found, note the regex; otherwise leave default.
- **languages** — from file extensions present.
- **subjectNoun** — the thing under review (e.g. `plugin`, `service`, `feature`) from the repo
  description or `package.json`/`plugin.json` name. Default `extension` if unclear.
- **existing PR template** — `.github/PULL_REQUEST_TEMPLATE*` or `.github/PULL_REQUEST_TEMPLATE/`.
  If present, note it (eval-pack should reuse it, not invent its own).
- **monorepo** — multiple `package.json`/workspaces.

## Step 2: Propose — a draft where every key carries its why

**Re-running setup (idempotency):** if `.eval-pack.json` already exists, READ it first and treat
the user's existing values as authoritative — propose changes as a diff on top, and never silently
overwrite a hand-edited key. Confirm before changing any value the user already set.


Render a proposed `.eval-pack.json` as a diff and tag each key by origin: `detected`, `chosen`,
or `default`. Reference the JSON Schema so editors validate it:

```json
{
  "$schema": "./.eval-pack.schema.json",
  "testCommands": ["npm test"],
  "ticketPattern": "ABC-\\d+",
  "subjectNoun": "plugin"
}
```

Only include keys that differ from the defaults or that the user chooses — an empty/omitted key
means "use the shipped default". Never write a guessed value for something you could not detect;
leave it out and say so.

## Step 3: Confirm — only the genuinely ambiguous, in domain language

Use `AskUserQuestion`. Ask about OUTCOMES, never enum names — map the answer to a config value:

- "How strict should reviews read?" → `analysisStance`: `skeptical-reviewer` (default) /
  `collaborative-coach` / `compliance-auditor`.
- "Any secrets in transcripts to mask?" → `redaction` (regex patterns) and whether to keep the
  openable copy local (`publishOpenable`).
- "Extend a shared team config?" → `extends: ["..."]`.

In Express mode, ask these as a single confirmation with the detected defaults pre-filled. In
Guided mode, walk each section. Do NOT ask about anything Step 1 already detected.

## Step 4: Write — config, local override, marketplace, gitignore

Write the files:

1. `.eval-pack.json` (committed) — the resolved choices from Steps 2–3. A value you could not
   detect and the user did not set is OMITTED with a note in your report, never written as a
   silent default.
2. `.eval-pack.local.json` (gitignored) — only if the user has per-developer secrets/redaction
   they don't want committed. Otherwise skip it.
3. `.eval-pack.schema.json` (committed) — copy it from
   `${CLAUDE_PLUGIN_ROOT}/schema/eval-pack.schema.json` so the `$schema` reference resolves
   offline and editors validate immediately:

   ```bash
   cp "${CLAUDE_PLUGIN_ROOT}/schema/eval-pack.schema.json" .eval-pack.schema.json
   ```

4. `.claude/settings.json` — register the marketplace (merge into existing content; create if
   absent):

```json
{
  "extraKnownMarketplaces": {
    "eval-pack": {
      "source": { "source": "github", "repo": "smalls257/eval-pack" }
    }
  }
}
```

5. `.gitignore` — ensure these lines exist (create the file if missing):

```
# Eval packs live on PR branches, not main
.eval-packs/

# Per-developer config override (never committed)
.eval-pack.local.json
```

## Step 5: Validate — dry-parse before claiming done

Run the resolver in check mode against the repo root and surface the result. A typo'd key or a
bad value HALTS here, at setup time, instead of becoming a silent no-op three reports later:

```bash
PYTHON="${CLAUDE_PLUGIN_OPTION_pythonExecutable:-python3}"
"$PYTHON" "${CLAUDE_PLUGIN_ROOT}/scripts/resolve_config.py" "$(pwd)" --check
```

If it prints `config valid`, report success. If it exits non-zero, show the user the stderr
verbatim and fix the offending key before finishing — do not leave an invalid config in place.

## Step 6: Report

Tell the user:
- What was written, and for each `.eval-pack.json` key whether it was detected / chosen / default.
- Any value that could NOT be detected and was left to the default (so nothing is a silent guess).
- New devs who clone the repo must install the plugin once:
  `/plugin marketplace add smalls257/eval-pack` then `/plugin install eval-pack@eval-pack`.
- They can now use `/eval-pack:generate` and `/eval-pack:review`; re-run `/eval-pack:setup` any
  time to adjust the configuration.
- The full customization surface, grouped: prompts (stance/rubric/retrospectiveQuestions/
  evaluatorPromptFile), heuristics (detectionPatterns/flagSeverities/thresholds/costBudgetTokens/
  customDetectors/detectorScripts for your own deterministic policy checks), tests & tickets
  (testCommands/ticketPattern), security (redaction/publishOpenable), report
  (branding/templateDir/sections), and extension lenses (analysisLenses + verdictAggregation) —
  with a pointer to the README Configuration section, `.eval-pack.schema.json` for details, and
  `/eval-pack:tune` for a fast re-evaluate loop after config changes.

## Extending in your own space (no plugin-source edits)

Everything a team adds lives in **their** repo, not the plugin:
- **Custom stance** — drop `.eval-pack/stances/<name>.md` in the repo and set
  `"analysisStance": "<name>"`. It wins over the bundled presets (project-first).
- **Custom evaluator guidance** — point `"evaluatorPromptFile"` at a file in the repo.
- **Custom lenses** — add `{"skill": "<your-skill>", "role": "contributor|scorer"}` to
  `analysisLenses` and provide `<your-skill>` as your own skill/agent (in `.claude/agents/` or
  your own plugin). eval-pack dispatches it and collects its `lenses/<skill>.json`; no eval-pack
  source change is needed. `requirement-drift` and `verification-rigor` are bundled examples.
- **Rubric, redaction, thresholds, friction categories, branding** — all plain `.eval-pack.json`.
