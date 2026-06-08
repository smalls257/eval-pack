# eval-pack

A Claude Code plugin that generates eval packs — polished HTML reports capturing how AI-assisted code was produced. Designed for PR review workflows where reviewers need visibility into agent behavior, not just the diff.

## Screenshots

![Eval Pack — header, completion status, verdict, and session metrics](docs/screenshots/hero.png)

![Session metrics — per-model token breakdown, cost, and session stats](docs/screenshots/metrics.png)

![Tools tab — tool usage bar chart and subagents dispatched](docs/screenshots/tools.png)

## What's in an Eval Pack?

- **Verdict banner** — pass/fail based on agent-driven test results
- **Visual evidence** — screenshots from Playwright or browser verification
- **Session metrics** — per-model token breakdown (controller + subagents), API cost estimate, turns, files changed
- **Session timeline** — human-readable narrative of what happened during the session
- **Heuristic flags** — false completions, retries, scope drift, test failures
- **Claude analysis** — retrospective, repo friction report, prompt quality assessment
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

In your project's `.claude/settings.json`:

```json
{
  "pluginConfigs": {
    "eval-pack": {
      "options": {
        "outputDir": ".eval-packs",
        "includeTranscript": true,
        "analysis": true
      }
    }
  }
}
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `outputDir` | string | `.eval-packs` | Directory where eval packs are written, relative to project root |
| `includeTranscript` | boolean | `true` | Include the full conversation transcript in the eval pack |
| `analysis` | boolean | `true` | Enable Claude retrospective analysis. When false, only heuristic flags are included |

## How It Works

1. Dev (or agent) runs `/eval-pack:generate`
2. Scripts extract metrics and detect heuristic patterns from the transcript
3. Claude runs appropriate tests, captures screenshots and logs
4. Claude analyzes the session — retrospective, repo friction, prompt quality
5. HTML report is rendered with all data, zipped to `.eval-packs/<session-id>.zip`
6. `/eval-pack:review` commits the zip to the branch and creates a PR
7. Reviewer downloads zip from the branch, extracts, opens `index.html`

## Output

`/eval-pack:generate` writes a portable `.zip` into your `outputDir` (default `.eval-packs/`)
**and** an uncompressed, openable copy into your system temp directory. The command prints an
`Open: file://…/index.html` path — open it directly in a browser, no unzip required. The zip is
what `/eval-pack:review` commits to a PR branch.

The analysis is written by an independent `eval-pack-evaluator` sub-agent, not by the agent that
did the work, so the evaluation is not self-graded. When the `analysis` option is `false`, the
pack renders an explicit "analysis disabled" banner instead of an AI evaluation.

## License

MIT
