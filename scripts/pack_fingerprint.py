#!/usr/bin/env python3
# scripts/pack_fingerprint.py
"""Content-hash reuse keys for delta re-runs. Keyed by the lens's ACTUAL input
bytes (its resolved view file) — never by turnId, which is a post-sort ordinal
that shifts under membership changes. A lens is reusable iff every input axis is
byte-identical to the prior round. Missing prior => reuse nothing (fail-safe)."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lens_versions  # noqa: E402


def lens_key(view_bytes, lens_version, model, diff_base):
    h = hashlib.sha256()
    for part in (view_bytes, str(lens_version).encode(), str(model).encode(), str(diff_base).encode()):
        h.update(hashlib.sha256(part).digest())   # length-framed
    return h.hexdigest()


def _view_bytes(pack_dir, view):
    p = Path(pack_dir) / ("transcript.jsonl" if view in (None, "full")
                          else "views/{}.jsonl".format(view))
    return p.read_bytes() if p.is_file() else b""


def compute(pack_dir, lenses, diff_base):
    """`lenses` = resolved analysisLenses [{skill, model?, ...}] with a resolved `view`."""
    lock = lens_versions.load_lock()
    per = {}
    for l in lenses:
        skill = l.get("skill")
        ver = (lock.get(skill) or {}).get("version", "?")
        per[skill] = lens_key(_view_bytes(pack_dir, l.get("view")), ver, l.get("model"), diff_base)
    whole = hashlib.sha256(json.dumps(per, sort_keys=True).encode()).hexdigest()
    return {"perLens": per, "whole": whole}


def decide_reuse(prior, current):
    if not prior or not isinstance(prior, dict):
        return {"reuseAll": False, "reuse": set(), "rerun": set(current["perLens"])}
    if prior.get("whole") == current.get("whole"):
        return {"reuseAll": True, "reuse": set(current["perLens"]), "rerun": set()}
    prior_p = prior.get("perLens") or {}
    reuse = {s for s, k in current["perLens"].items() if prior_p.get(s) == k}
    rerun = set(current["perLens"]) - reuse
    return {"reuseAll": False, "reuse": reuse, "rerun": rerun}


def _read_json_or_none(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _run_decide(prior_path, current_path):
    prior = _read_json_or_none(prior_path)
    current = _read_json_or_none(current_path)
    if current is None:
        raise SystemExit("pack_fingerprint --decide: unreadable current fingerprint: {}".format(current_path))
    decision = decide_reuse(prior, current)
    out = {
        "reuseAll": decision["reuseAll"],
        "reuse": sorted(decision["reuse"]),
        "rerun": sorted(decision["rerun"]),
    }
    print(json.dumps(out))
    return 0


def _run_compute(pack_dir, config_path, diff_base):
    cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
    lenses = cfg.get("analysisLenses") or []
    # resolve each lens's declared view (reuse lens_inputs.declared_view over its .md)
    import lens_inputs
    lens_dir = Path(__file__).resolve().parent.parent / "agents" / "lenses"
    for l in lenses:
        md = lens_dir / (l.get("skill", "") + ".md")
        l["view"] = lens_inputs.declared_view(md.read_text(encoding="utf-8")) if md.is_file() else "full"
    out = compute(pack_dir, lenses, diff_base)
    (Path(pack_dir) / "pack-fingerprint.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("pack-fingerprint.json: {} lenses".format(len(out["perLens"])))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("pack_dir", nargs="?", help="pack directory (normal compute mode)")
    ap.add_argument("--config", help="resolved eval-config.json (normal compute mode)")
    ap.add_argument("--diff-base", default="")
    ap.add_argument("--decide", nargs=2, metavar=("PRIOR_FINGERPRINT_JSON", "CURRENT_FINGERPRINT_JSON"),
                     help="print decide_reuse(prior, current) as JSON; mutually exclusive with compute mode")
    args = ap.parse_args(argv)

    if args.decide:
        if args.pack_dir is not None or args.config is not None:
            ap.error("--decide is mutually exclusive with pack_dir/--config (normal compute mode)")
        return _run_decide(args.decide[0], args.decide[1])

    if not args.pack_dir or not args.config:
        ap.error("pack_dir and --config are required in normal compute mode")
    return _run_compute(args.pack_dir, args.config, args.diff_base)


if __name__ == "__main__":
    sys.exit(main())
