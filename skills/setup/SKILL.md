---
description: Bootstrap a repository to use eval-pack — copies GitHub Action, adds config, sets up gitignore and Pages. Run once per repo.
tags: ["setup", "config"]
---

# Setup Eval Pack

Bootstrap the current repository to use eval-pack. Follow these steps:

## Step 1: Add Submodule

If eval-pack is not already a submodule in this repo:

```bash
git submodule add https://github.com/smalls257/eval-pack .claude/plugins/eval-pack
```

## Step 2: Register Plugin

Check if `.claude/settings.json` exists. If it does, merge into it. If not, create it.

Add this configuration (preserve any existing content):

```json
{
  "extraKnownMarketplaces": {
    "eval-pack": {
      "source": {
        "source": "local",
        "path": "./.claude/plugins/eval-pack"
      }
    }
  },
  "enabledPlugins": {
    "eval-pack@eval-pack": true
  }
}
```

## Step 3: Copy GitHub Action

```bash
mkdir -p .github/workflows
cp "${CLAUDE_PLUGIN_ROOT}/templates/workflows/eval-pack-pages.yml" .github/workflows/eval-pack-pages.yml
```

## Step 4: Update .gitignore

Add to the project's `.gitignore` (create if missing):

```
# Eval packs live on PR branches and gh-pages, not main
.eval-packs/
```

## Step 5: Setup GitHub Pages

If the `gh` CLI is available and authenticated:

```bash
gh api repos/{owner}/{repo}/pages -X POST -f source='{"branch":"gh-pages","path":"/"}' 2>/dev/null || true
```

If this fails, tell the user to enable GitHub Pages manually on the `gh-pages` branch.

## Step 6: Report

Tell the user:
- What was set up
- Remind them to commit `.claude/settings.json`, `.gitmodules`, and `.github/workflows/eval-pack-pages.yml`
- Devs need to run `git submodule update --init` after cloning
- They can now use `/eval-pack:generate` and `/eval-pack:review`
