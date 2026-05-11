---
description: Bootstrap a repository to use eval-pack — copies GitHub Action, adds config, sets up gitignore and Pages. Run once per repo.
tags: ["setup", "config"]
---

# Setup Eval Pack

Bootstrap the current repository to use eval-pack. Follow these steps:

## Step 1: Add Submodule

If eval-pack is not already a submodule in this repo:

```bash
git submodule add https://github.com/smalls257/eval-pack .claude/skills/eval-pack
```

Claude Code auto-discovers skills from `.claude/skills/` — no extra config needed.

## Step 2: Copy GitHub Action

Copy the eval-pack Pages deployment workflow into the target repo:

```bash
mkdir -p .github/workflows
cp "${CLAUDE_PLUGIN_ROOT}/templates/workflows/eval-pack-pages.yml" .github/workflows/eval-pack-pages.yml
```

## Step 3: Update .gitignore

Add `.eval-packs/` to the project's `.gitignore` file. If `.gitignore` doesn't exist, create it.

```
# Eval packs live on PR branches and gh-pages, not main
.eval-packs/
```

## Step 4: Setup GitHub Pages

If the `gh` CLI is available and authenticated:

```bash
gh api repos/{owner}/{repo}/pages -X POST -f source='{"branch":"gh-pages","path":"/"}' 2>/dev/null || true
```

If this fails (Pages may already be enabled, or permissions may not allow it), inform the user they need to enable GitHub Pages manually on the `gh-pages` branch.

## Step 5: Report

Tell the user:
- What was set up
- Remind them to commit the changes
- Tell them devs need to run `git submodule update --init` after cloning
- They can now use `/eval-pack:generate` and `/eval-pack:review`
