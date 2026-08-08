#!/usr/bin/env python3
"""Resolve and validate eval-pack config, writing the single eval-config.json.

Usage:
  resolve_config.py <project_root> <pack_dir>   # write <pack_dir>/eval-config.json
  resolve_config.py <project_root> --check       # validate only, no write
On a hard validation error: print to stderr and exit 1, writing nothing.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))  # noqa: E402
import config  # noqa: E402


def _confined_repo_file(project_root, entry):
    """Return an error string unless entry resolves to an existing file inside project_root.

    Confine to the repo (same rule as extends presets): reject ../ escapes and
    absolute out-of-repo paths — Path(root) / absolute yields the absolute path.
    """
    root_resolved = Path(project_root).resolve()
    path = Path(project_root) / entry
    resolved = path.resolve()
    if not (resolved == root_resolved or root_resolved in resolved.parents):
        return "resolves outside the repo"
    if not path.is_file():
        return "not found under {}".format(project_root)
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description="Resolve eval-pack configuration")
    parser.add_argument("project_root", help="Repo root containing .eval-pack.json")
    parser.add_argument("pack_dir", nargs="?", help="Pack dir to write eval-config.json into")
    parser.add_argument("--check", action="store_true", help="Validate only; write nothing")
    args = parser.parse_args(argv)

    try:
        cfg = config.load_config(args.project_root)
    except config.ConfigError as exc:
        # Malformed input (bad JSON / uncoercible env value) — surface with context, halt.
        print("ERROR: " + str(exc), file=sys.stderr)
        return 1
    errors = config.validate(cfg)
    if errors:
        for e in errors:
            print("ERROR: " + e, file=sys.stderr)
        return 1

    plugin_root = Path(__file__).resolve().parent.parent
    stance = cfg.get("analysisStance", "")
    # Project-first: a custom stance lives in the user's own repo (.eval-pack/stances/<name>.md),
    # with the bundled presets as fallback — so a custom stance needs NO plugin-source edit.
    candidates = [
        Path(args.project_root) / ".eval-pack" / "stances" / (stance + ".md"),
        plugin_root / "presets" / "stances" / (stance + ".md"),
    ]
    preset = next((p for p in candidates if p.is_file()), None)
    if preset is None:
        print(
            "ERROR: unknown analysisStance {!r} — no preset at .eval-pack/stances/{}.md "
            "(your repo) or the bundled presets/stances/".format(stance, stance),
            file=sys.stderr,
        )
        return 1
    cfg["analysisStanceText"] = preset.read_text(encoding="utf-8")

    prompt_file = cfg.get("evaluatorPromptFile") or ""
    if prompt_file:
        err = _confined_repo_file(args.project_root, prompt_file)
        if err:
            print("ERROR: evaluatorPromptFile {!r} {}".format(prompt_file, err), file=sys.stderr)
            return 1

    for script in cfg.get("detectorScripts") or []:
        err = _confined_repo_file(args.project_root, script)
        if err:
            print("ERROR: detectorScripts entry {!r} {}".format(script, err), file=sys.stderr)
            return 1

    for lens in cfg.get("analysisLenses") or []:
        tpl = lens.get("template")
        if tpl:
            err = _confined_repo_file(args.project_root, tpl)
            if err:
                print("ERROR: analysisLenses template {!r} {}".format(tpl, err), file=sys.stderr)
                return 1
            # Embed the trusted repo markup so the pack is self-contained (mirrors stance embedding).
            lens["templateHtml"] = (Path(args.project_root) / tpl).read_text(encoding="utf-8")

    # Sensor: a verdict config where every failure-capable flag is disabled can never fail —
    # warn, don't block. Derived from FAILURE_FLAG_IDS so it can't rot when flags are added.
    sev = cfg.get("flagSeverities") or {}
    if sev and all(sev.get(fid) == "off" for fid in config.FAILURE_FLAG_IDS):
        print(
            "WARNING: flagSeverities disables every failure-capable flag — this verdict "
            "config can never fail. Intended?",
            file=sys.stderr,
        )

    if args.check:
        print("config valid")
        return 0

    if not args.pack_dir:
        print("ERROR: pack_dir is required unless --check is given", file=sys.stderr)
        return 2

    out = Path(args.pack_dir) / "eval-config.json"
    out.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    print("resolved config -> " + str(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
