#!/usr/bin/env python3
"""Assemble per-lens outputs into lenses.json and compute the aggregated verdict score.

Each configured lens (dispatched as a subagent by the generate skill) writes one file
`PACK_DIR/lenses/<id>.json`. This script collects them, reads the core confidence from
analysis.json and the aggregation rule from eval-config.json, and writes `PACK_DIR/lenses.json`
with contributors, scorers, failures, and the transparent aggregation math (Guard G2). Keeping
the aggregation in a tested script — not orchestration prose — makes the verdict auditable.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))  # noqa: E402
import aggregate  # noqa: E402
import config  # noqa: E402


def assemble(pack_dir):
    pack = Path(pack_dir)
    lens_dir = pack / "lenses"
    results = []
    if lens_dir.is_dir():
        for f in sorted(lens_dir.glob("*.json")):
            try:
                r = json.loads(f.read_text(encoding="utf-8"))
                r.setdefault("skill", f.stem)
                results.append(r)
            except (json.JSONDecodeError, OSError):
                results.append({"skill": f.stem, "role": "unknown",
                                "error": "malformed or unreadable lens output"})

    def _ok(r):
        return "error" not in r

    contributors = [r for r in results if r.get("role") == "contributor" and _ok(r)]
    scorers = [r for r in results if r.get("role") == "scorer" and _ok(r)
               and isinstance(r.get("score"), (int, float)) and not isinstance(r.get("score"), bool)]
    # A scorer that ran but returned a non-numeric score is a failure, not silently dropped.
    failures = [r for r in results if not _ok(r)
                or (r.get("role") == "scorer" and r not in scorers)]

    cfg_path = pack / "eval-config.json"
    cfg = config.read_config(str(cfg_path)) if cfg_path.is_file() else config.read_config()
    rule = cfg.get("verdictAggregation", "core")

    analysis_path = pack / "analysis.json"
    analysis = {}
    if analysis_path.is_file():
        try:
            analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            analysis = {}
    core = (analysis.get("highlights") or {}).get("confidencePercent")

    out = {"rule": rule, "contributors": contributors, "scorers": scorers, "failures": failures}
    if isinstance(core, (int, float)) and not isinstance(core, bool):
        out["coreScore"] = core
        if scorers:
            try:
                out["finalScore"] = aggregate.aggregate(core, [s["score"] for s in scorers], rule)
            except ValueError as exc:
                out["aggregationError"] = str(exc)
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description="Assemble lens outputs into lenses.json")
    parser.add_argument("pack_dir")
    args = parser.parse_args(argv)
    out = assemble(args.pack_dir)
    (Path(args.pack_dir) / "lenses.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("lenses.json: {} contributors, {} scorers, {} failures".format(
        len(out["contributors"]), len(out["scorers"]), len(out["failures"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
