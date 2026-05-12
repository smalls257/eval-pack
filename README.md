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

- **Python 3** — required by the generation scripts (`extract-metrics.sh`, `render-html.sh`)
- **jq** — used for JSON processing throughout
- **zip** — used to package the eval pack output
- **gh** CLI — required by `/eval-pack:review` to create PRs and post comments

## Install

In Claude Code, run:

```
/plugin marketplace add smalls257/eval-pack
/plugin install eval-pack@eval-pack
```

Then run the setup skill to wire up the GitHub Action and gitignore:

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

Generates the eval pack, commits the zip to the current branch, creates (or updates) a PR, and posts a summary comment. The GitHub Action uploads the zip as a private artifact once the PR runs CI.

### Agent auto-generation

Agents can invoke `/eval-pack:generate` autonomously when they judge work is PR-ready. No hooks required — the agent calls the skill like any other.

## Configuration

In your project's `.claude/settings.json`:

```json
{
  "pluginConfigs": {
    "eval-pack": {
      "options": {
        "analysis": true
      }
    }
  }
}
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `analysis` | boolean | `true` | Enable Claude retrospective analysis |

## How It Works

1. Dev (or agent) runs `/eval-pack:generate`
2. Scripts extract metrics and detect heuristic patterns from the transcript
3. Claude runs appropriate tests, captures screenshots and logs
4. Claude analyzes the session — retrospective, repo friction, prompt quality
5. HTML report is rendered with all data
6. `/eval-pack:review` optionally creates a PR and posts a summary comment
7. GitHub Action uploads the zip as a private artifact
8. Reviewer downloads zip from the Actions tab, extracts, opens `index.html`

## License

MIT
