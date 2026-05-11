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

## Install

**1. Add as a git submodule:**

```bash
git submodule add https://github.com/smalls257/eval-pack .claude/skills/eval-pack
```

Claude Code auto-discovers skills from `.claude/skills/` — no extra config needed.

**2. Run the setup skill** to wire up the GitHub Action, gitignore, and Pages config:

```
/eval-pack:setup
```

After cloning a repo with eval-pack already installed, devs run:

```bash
git submodule update --init
```

## Usage

### Generate an eval pack

```
/eval-pack:generate
```

Produces a self-contained HTML report in `.eval-packs/<session-id>/`. Open `index.html` in a browser.

### Generate + create PR

```
/eval-pack:review
```

Generates the eval pack, creates (or updates) a PR, and posts a summary comment with a link to the deployed eval pack on GitHub Pages.

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
        "redactPatterns": ["\\.env", "SECRET"],
        "analysis": true,
        "pagesBaseUrl": "https://myorg.github.io/myrepo/eval-packs"
      }
    }
  }
}
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `outputDir` | string | `.eval-packs` | Where eval packs are written |
| `includeTranscript` | boolean | `true` | Include full conversation in pack |
| `redactPatterns` | string[] | `[]` | Regex patterns to strip from transcript |
| `analysis` | boolean | `true` | Enable Claude retrospective analysis |
| `pagesBaseUrl` | string | — | Base URL for GitHub Pages links |

## How It Works

1. Dev (or agent) runs `/eval-pack:generate`
2. Scripts extract metrics and detect heuristic patterns from the transcript
3. Claude runs appropriate tests, captures screenshots and logs
4. Claude analyzes the session — retrospective, repo friction, prompt quality
5. HTML report is rendered with all data
6. `/eval-pack:review` optionally creates a PR and posts a summary comment
7. GitHub Action deploys the HTML to `gh-pages` branch
8. Reviewer clicks the link in the PR comment to view the full eval pack

## License

MIT
