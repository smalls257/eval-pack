#!/usr/bin/env python3
# scripts/pack_cost.py
"""Aggregate eval-pack's OWN per-lens token spend into pack-cost.json.

The per-lens count lives only in the parent orchestrator's Agent tool result
(a lens subagent cannot see its own usage), so generate/tune write a one-integer
sidecar `lenses/<skill>.cost.json` per dispatch. This script aggregates them
deterministically — it never trusts the LLM to do math, only to copy one int.
A missing/malformed sidecar for a configured lens is a RECORDED GAP, not a 0."""
import argparse
import json
import sys
from pathlib import Path

_EVALUATOR = "eval-pack-evaluator"


def _gap(skill, reason):
    # Every gap row carries the same key set as a normal row (model, reused)
    # so downstream consumers can do entry["model"] unconditionally instead
    # of branching on whether the row is a gap.
    return {"skill": skill, "tokens": None, "gap": reason, "model": None, "reused": None}


def _read_sidecar(path):
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        skill = path.stem[:-5] if path.stem.endswith(".cost") else path.stem
        return _gap(skill, "unreadable sidecar ({})".format(exc))
    tokens = d.get("tokens")
    if not isinstance(tokens, int) or isinstance(tokens, bool):
        return _gap(d.get("skill", path.stem), "non-integer tokens")
    return {"skill": d.get("skill", path.stem), "tokens": tokens,
            "model": d.get("model"), "reused": bool(d.get("reused", False))}


def aggregate(pack_dir, expected_skills=None):
    pack = Path(pack_dir)
    lens_dir = pack / "lenses"
    entries = []
    if lens_dir.is_dir():
        for f in sorted(lens_dir.glob("*.cost.json")):
            entries.append(_read_sidecar(f))
    if expected_skills is not None:
        seen = {e["skill"] for e in entries}
        for skill in expected_skills:
            if skill not in seen:
                entries.append(_gap(skill, "missing sidecar"))
    per_lens = [e for e in entries if e["skill"] != _EVALUATOR]
    evaluator_entry = next((e for e in entries if e["skill"] == _EVALUATOR), None)
    evaluator = evaluator_entry["tokens"] if evaluator_entry and isinstance(evaluator_entry["tokens"], int) else 0
    total = sum(e["tokens"] for e in entries if isinstance(e["tokens"], int))
    # Top-level gaps list covers EVERY sidecar that resolved to a gap, whether
    # it's a perLens entry or the evaluator's own sidecar — evaluatorTokens
    # defaulting to 0 on a gap must never be the only signal a caller sees.
    gaps = [e["skill"] for e in entries if e["tokens"] is None]
    return {"perLens": per_lens, "evaluatorTokens": evaluator, "totalTokens": total, "gaps": gaps}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Aggregate per-lens eval-pack cost")
    ap.add_argument("pack_dir")
    ap.add_argument("--expect-skills", default=None,
                     help="Comma-separated skill names expected to have a sidecar; any without "
                          "one becomes a recorded gap (catches a lens that crashed before writing).")
    args = ap.parse_args(argv)
    expected_skills = None
    if args.expect_skills:
        expected_skills = [s.strip() for s in args.expect_skills.split(",") if s.strip()] or None
    out = aggregate(args.pack_dir, expected_skills=expected_skills)
    (Path(args.pack_dir) / "pack-cost.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    gaps = out["gaps"]
    print("pack-cost.json: {} lenses, total {} tokens{}".format(
        len(out["perLens"]), out["totalTokens"],
        "" if not gaps else " (gaps: {})".format(", ".join(gaps))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
