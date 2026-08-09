"""Orchestrate the five lens-evaluation checks over a committed bundle + collected trials."""
import argparse
import json
import sys
from pathlib import Path

from lens_manifest import parse_basis
from lens_checks import (
    evidence_resolution, rule_consistency, reference_resolution,
    claim_coverage, output_assertion,
)


def _read_json(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def _corpus(fixture_dir):
    text = (fixture_dir / "transcript.jsonl").read_text(encoding="utf-8")
    patch = fixture_dir / "delivered.patch"
    if patch.is_file():
        text += "\n" + patch.read_text(encoding="utf-8")
    return text


def evaluate_bundle(bundle_dir, trials_dir, contract):
    bundle_dir, trials_dir = Path(bundle_dir), Path(trials_dir)
    basis = parse_basis((bundle_dir / "basis.md").read_text(encoding="utf-8"))
    ledger = _read_json(bundle_dir / "provenance.json")
    gold = _read_json(bundle_dir / "gold.json")
    ordinal = contract.get("levelOrdinal") or []
    fkey = contract.get("findingsKey", "findings")
    fixture_ids = set(gold.keys())

    checks = {
        "reference_resolution": reference_resolution(basis.get("sources", []), ledger),
        "claim_coverage": claim_coverage(basis.get("claims", []), fixture_ids),
    }

    fixtures = {}
    for fid in fixture_ids:
        fixdir = bundle_dir / "fixtures" / fid
        corpus = _corpus(fixdir)
        trials = [_read_json(p) for p in sorted((trials_dir / fid).glob("trial-*.json"))]
        ev = [evidence_resolution(t, corpus, findings_key=fkey) for t in trials]
        rc = [rule_consistency(t, basis.get("rules", []), ordinal, findings_key=fkey) for t in trials]
        oa = output_assertion(trials, gold[fid], ordinal, findings_key=fkey)
        fixtures[fid] = {
            "evidence_ok": all(p for p, _ in ev),
            "rules_ok": all(p for p, _ in rc),
            "assertion": oa,
        }

    passed = (
        checks["reference_resolution"][0] and checks["claim_coverage"][0]
        and all(f["evidence_ok"] and f["rules_ok"] and f["assertion"]["passed"]
                for f in fixtures.values())
    )
    return {"lens": bundle_dir.name, "passed": passed, "checks": checks, "fixtures": fixtures}


def _fmt(report):
    lines = ["lens {}: {}".format(report["lens"], "PASS" if report["passed"] else "FAIL")]
    for name, (ok, msgs) in report["checks"].items():
        lines.append("  {}: {}".format(name, "ok" if ok else "FAIL " + "; ".join(msgs)))
    for fid, f in report["fixtures"].items():
        a = f["assertion"]
        flag = "" if a["meeting"] == a["n"] else " (flaky)"
        lines.append("  {}: evidence={} rules={} assertion={}/{}{}".format(
            fid, f["evidence_ok"], f["rules_ok"], a["meeting"], a["n"], flag))
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("bundle_dir")
    ap.add_argument("trials_dir")
    ap.add_argument("--contract", required=True, help="path to output-contract JSON")
    args = ap.parse_args(argv)
    report = evaluate_bundle(args.bundle_dir, args.trials_dir, _read_json(args.contract))
    print(_fmt(report))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
