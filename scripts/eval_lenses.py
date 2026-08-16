"""Orchestrate the five lens-evaluation checks over a committed bundle + collected trials."""
import argparse
import json
import sys
from pathlib import Path

from lens_manifest import parse_basis
from lens_checks import (
    evidence_resolution, rule_consistency, reference_resolution,
    claim_coverage, output_assertion, guidance_completeness,
)


def _read_json(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def _corpus(fixture_dir, roles=None):
    """Concatenated transcript text for evidence resolution. `roles` (e.g. ["assistant"]) restricts
    the corpus to those turns: an assistant-behavior lens (sycophancy) must resolve its quotes
    against the ASSISTANT's OWN words, so a quote lifted from a USER turn no longer spuriously
    resolves against the whole transcript (finding: sycophancy quoting user text)."""
    parts = []
    for line in (fixture_dir / "transcript.jsonl").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = d.get("message") or {}
        role = msg.get("role") or d.get("type") or d.get("role")
        if roles is not None and role not in roles:
            continue
        content = msg.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            parts.append(" ".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"))
    text = "\n".join(parts)
    # The delivered diff is authored evidence with no turn role — include it only for the
    # whole-corpus (roles=None) case so a diff-quoting lens still resolves. A role-restricted
    # corpus is specifically about turn provenance, so the patch stays out of it.
    if roles is None:
        patch = fixture_dir / "delivered.patch"
        if patch.is_file():
            text += "\n" + patch.read_text(encoding="utf-8")
    return text


def _corpus_index(fixture_dir, roles=None):
    """Map turnId -> {'text', 'truncated'} for turnId-based evidence resolution.
    turnId is the record's own or its 0-based file position (legacy fixtures)."""
    index = {}
    lines = (fixture_dir / "transcript.jsonl").read_text(encoding="utf-8").splitlines()
    for pos, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = d.get("message") or {}
        role = msg.get("role") or d.get("type") or d.get("role")
        if roles is not None and role not in roles:
            continue
        tid = d.get("turnId", pos)
        content = msg.get("content")
        text, truncated = "", False
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            texts = []
            for b in content:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "text":
                    texts.append(b.get("text", ""))
                if b.get("_truncated"):
                    truncated = True
            text = " ".join(texts)
        index[tid] = {"text": text, "truncated": truncated}
    return index


def evaluate_bundle(bundle_dir, trials_dir, contract):
    bundle_dir, trials_dir = Path(bundle_dir), Path(trials_dir)
    basis = parse_basis((bundle_dir / "basis.md").read_text(encoding="utf-8"))
    ledger = _read_json(bundle_dir / "provenance.json")
    gold = _read_json(bundle_dir / "gold.json")
    ordinal = contract.get("levelOrdinal") or []
    fkey = contract.get("findingsKey", "findings")
    tfield = contract.get("typeField", "type")
    fixture_ids = set(gold.keys())

    checks = {
        "reference_resolution": reference_resolution(basis.get("sources", []), ledger),
        "claim_coverage": claim_coverage(basis.get("claims", []), fixture_ids),
    }

    fixtures = {}
    for fid in fixture_ids:
        fixdir = bundle_dir / "fixtures" / fid
        # evidenceRoles (from the lens output contract) restricts the evidence corpus to those
        # turns — e.g. sycophancy declares ["assistant"] so a finding must quote the assistant.
        corpus = _corpus(fixdir, roles=contract.get("evidenceRoles"))
        turn_index = _corpus_index(fixdir, roles=contract.get("evidenceRoles"))
        require_tid = contract.get("requiresTurnId", False)
        trials = [_read_json(p) for p in sorted((trials_dir / fid).glob("trial-*.json"))]
        ev = [evidence_resolution(t, corpus, findings_key=fkey,
                                  turn_index=turn_index, require_turn_id=require_tid) for t in trials]
        rc = [rule_consistency(t, basis.get("rules", []), ordinal, findings_key=fkey, type_field=tfield) for t in trials]
        oa = output_assertion(trials, gold[fid], ordinal, findings_key=fkey)
        # A lens that declares requiresGuidance must carry the why-it-matters / do-next banners
        # (summary + per non-exempt finding); an output missing them fails deterministically.
        if contract.get("requiresGuidance"):
            guidance_ok = all(guidance_completeness(t, findings_key=fkey,
                                                    exempt_types=contract.get("guidanceExemptTypes"),
                                                    type_field=tfield)[0] for t in trials)
        else:
            guidance_ok = True
        fixtures[fid] = {
            "evidence_ok": all(p for p, _ in ev),
            "rules_ok": all(p for p, _ in rc),
            "guidance_ok": guidance_ok,
            "assertion": oa,
        }

    passed = (
        checks["reference_resolution"][0] and checks["claim_coverage"][0]
        and all(f["evidence_ok"] and f["rules_ok"] and f["guidance_ok"] and f["assertion"]["passed"]
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
