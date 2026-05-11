---
description: Bootstrap a repository to use eval-pack — copies GitHub Action, adds config, sets up gitignore and Pages. Run once per repo.
tags: ["setup", "config"]
---

# Setup Eval Pack

Bootstrap the current repository to use eval-pack. Follow these steps:

## Step 1: Copy GitHub Action

```bash
mkdir -p .github/workflows
cp "${CLAUDE_PLUGIN_ROOT}/templates/workflows/eval-pack-pages.yml" .github/workflows/eval-pack-pages.yml
```

## Step 2: Update .gitignore

Add to the project's `.gitignore` (create if missing):

```
# Eval packs live on PR branches and gh-pages, not main
.eval-packs/
```

## Step 3: Setup GitHub Pages

If the `gh` CLI is available and authenticated:

```bash
gh api repos/{owner}/{repo}/pages -X POST -f source='{"branch":"gh-pages","path":"/"}' 2>/dev/null || true
```

If this fails, tell the user to enable GitHub Pages manually on the `gh-pages` branch.

## Step 4: Report

Tell the user:
- What was set up
- Remind them to commit `.github/workflows/eval-pack-pages.yml`
- New devs who clone the repo must install the plugin once: `/plugin marketplace add smalls257/eval-pack` then `/plugin install eval-pack@eval-pack`
- They can now use `/eval-pack:generate` and `/eval-pack:review`
