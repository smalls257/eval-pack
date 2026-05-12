---
description: Bootstrap a repository to use eval-pack — adds config and sets up gitignore. Run once per repo.
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
  }
}
```

Note: New devs who clone this repo will need to run these commands once in Claude Code to install the plugin:
```
/plugin marketplace add smalls257/eval-pack
/plugin install eval-pack@eval-pack
```

## Step 2: Update .gitignore

Add to the project's `.gitignore` (create if missing):

```
# Eval packs are committed to PR branches, not main
.eval-packs/
```

## Step 3: Report

Tell the user:
- What was set up
- New devs who clone the repo must install the plugin once: `/plugin marketplace add smalls257/eval-pack` then `/plugin install eval-pack@eval-pack`
- They can now use `/eval-pack:generate` and `/eval-pack:review`
