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


def _read_sidecar(path):
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"skill": path.stem[:-5] if path.stem.endswith(".cost") else path.stem,
                "tokens": None, "gap": "unreadable sidecar ({})".format(exc)}
    tokens = d.get("tokens")
    if not isinstance(tokens, int) or isinstance(tokens, bool):
        return {"skill": d.get("skill", path.stem), "tokens": None,
                "gap": "non-integer tokens"}
    return {"skill": d.get("skill", path.stem), "tokens": tokens,
            "model": d.get("model"), "reused": bool(d.get("reused", False))}


def aggregate(pack_dir):
    pack = Path(pack_dir)
    lens_dir = pack / "lenses"
    entries = []
    if lens_dir.is_dir():
        for f in sorted(lens_dir.glob("*.cost.json")):
            entries.append(_read_sidecar(f))
    per_lens = [e for e in entries if e["skill"] != _EVALUATOR]
    evaluator = next((e["tokens"] for e in entries
                      if e["skill"] == _EVALUATOR and isinstance(e["tokens"], int)), 0)
    total = sum(e["tokens"] for e in entries if isinstance(e["tokens"], int))
    return {"perLens": per_lens, "evaluatorTokens": evaluator, "totalTokens": total}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Aggregate per-lens eval-pack cost")
    ap.add_argument("pack_dir")
    args = ap.parse_args(argv)
    out = aggregate(args.pack_dir)
    (Path(args.pack_dir) / "pack-cost.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    gaps = [e["skill"] for e in out["perLens"] if e["tokens"] is None]
    print("pack-cost.json: {} lenses, total {} tokens{}".format(
        len(out["perLens"]), out["totalTokens"],
        "" if not gaps else " (gaps: {})".format(", ".join(gaps))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
