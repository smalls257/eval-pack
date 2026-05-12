---
description: Bootstrap a repository to use eval-pack — copies GitHub Action, adds config, sets up gitignore. Run once per repo.
tags: ["setup", "config"]
---

# Setup Eval Pack

Bootstrap the current repository to use eval-pack. Follow these steps:

## Step 1: Register Plugin

Check if `.claude/settings.json` exists. If it does, merge into it. If not, create it.

Add this configuration (preserve any existing content):

```json
{
  "extraKnownMarketplaces": {
    "eval-pack": {
      "source": {
        "source": "github",
        "repo": "smalls257/eval-pack"
      }
    }
  },
  "enabledPlugins": {
    "eval-pack@eval-pack": true
  }
}
```

Note: New devs who clone this repo will need to run these commands once in Claude Code to install the plugin:
```
/plugin marketplace add smalls257/eval-pack
/plugin install eval-pack@eval-pack
```

## Step 2: Copy GitHub Action

```bash
mkdir -p .github/workflows
cp "${CLAUDE_PLUGIN_ROOT}/templates/workflows/eval-pack.yml" .github/workflows/eval-pack.yml
```

## Step 3: Update .gitignore

Add to the project's `.gitignore` (create if missing):

```
# Eval packs are committed to PR branches, not main
.eval-packs/
```

## Step 4: Report

Tell the user:
- What was set up
- Remind them to commit `.github/workflows/eval-pack.yml`
- New devs who clone the repo must install the plugin once: `/plugin marketplace add smalls257/eval-pack` then `/plugin install eval-pack@eval-pack`
- Eval packs are uploaded as GitHub Actions artifacts on each PR — accessible from the Actions tab, private to repo collaborators
- They can now use `/eval-pack:generate` and `/eval-pack:review`
