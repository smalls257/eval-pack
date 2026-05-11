---
description: Bootstrap a repository to use eval-pack — copies GitHub Action, adds config, sets up gitignore and Pages. Run once per repo.
tags: ["setup", "config"]
---

# Setup Eval Pack

Bootstrap the current repository to use eval-pack. Follow these steps:

## Step 1: Copy GitHub Action

Copy the eval-pack Pages deployment workflow into the target repo:

```bash
mkdir -p .github/workflows
cp "${CLAUDE_PLUGIN_ROOT}/templates/workflows/eval-pack-pages.yml" .github/workflows/eval-pack-pages.yml
```

## Step 2: Add Plugin Config

Check if `.claude/settings.json` exists. If it does, merge eval-pack config into it. If not, create it.

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
  },
  "pluginConfigs": {
    "eval-pack": {
      "options": {
        "outputDir": ".eval-packs",
        "includeTranscript": true,
        "redactPatterns": [],
        "analysis": true,
        "pagesBaseUrl": ""
      }
    }
  }
}
```

Ask the user for their GitHub Pages base URL (format: `https://<org>.github.io/<repo>/eval-packs`) and fill it in.

## Step 3: Update .gitignore

Add `.eval-packs/` to the project's `.gitignore` file. If `.gitignore` doesn't exist, create it.

The entry should have a comment explaining why:

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

## Step 5: Add Submodule

If eval-pack is not already a submodule in this repo:

```bash
git submodule add <eval-pack-repo-url> .claude/plugins/eval-pack
```

Ask the user for the eval-pack repository URL if not obvious from context.

## Step 6: Report

Tell the user:
- What was set up
- Remind them to commit the changes
- Tell them to set `pagesBaseUrl` in `.claude/settings.json` if they didn't provide it
- Tell them devs need to run `git submodule update --init` after cloning
- They can now use `/eval-pack:generate` and `/eval-pack:review`
