"""The five lens-evaluation checks. Pure functions over on-disk-derived inputs."""
import re

from lens_rules import check_rules

_WS = re.compile(r"\s+")


def _norm(s):
    return _WS.sub(" ", (s or "")).strip()


def evidence_resolution(output, corpus, findings_key="findings"):
    """Atomic provenance: every evidential finding's quote must appear verbatim in the corpus."""
    hay = _norm(corpus)
    msgs = []
    for i, f in enumerate(output.get(findings_key) or []):
        if not f.get("evidential", True):
            continue
        q = _norm(f.get("quote"))
        if not q or q not in hay:
            msgs.append("{}[{}] quote unresolved: {!r}".format(findings_key, i, f.get("quote")))
    return (not msgs, msgs)


def rule_consistency(output, rules, ordinal, findings_key="findings", type_field="type"):
    """Output must satisfy the lens's own declared invariants (no ground truth).

    Only evidential findings may justify a rule's verdict (e.g. an
    at_least_one_in escalation) — a non-evidential finding cannot move it.

    `findings_key`/`type_field` let non-drift lenses (e.g. `items`/`kind`)
    reuse the closed-grammar rule evaluator: the evidential-filtered
    collection is normalized into a `{"findings": [{"type": ...}]}` shape
    so `lens_rules.py` stays untouched.
    """
    entries = [f for f in (output.get(findings_key) or []) if f.get("evidential", True)]
    normalized = {**output, "findings": [{"type": e.get(type_field)} for e in entries],
                  "level": output.get("level"), "score": output.get("score")}
    msgs = check_rules(rules, normalized, ordinal)
    return (not msgs, msgs)


def reference_resolution(sources, ledger):
    """Basis sources must match the committed provenance ledger (offline; no network)."""
    msgs = []
    for s in sources:
        sid = s.get("id")
        entry = ledger.get(sid)
        if entry is None:
            msgs.append("source {!r} missing from provenance ledger".format(sid))
        elif _norm(entry.get("title")).lower() != _norm(s.get("title")).lower():
            msgs.append("source {!r} title mismatch vs ledger".format(sid))
    return (not msgs, msgs)


def claim_coverage(claims, fixture_ids):
    """No-op test: every claim exercised by a real fixture; every fixture backs a claim."""
    msgs = []
    covered = set()
    for c in claims:
        covers = c.get("covers") or []
        if not covers:
            msgs.append("claim {!r} covers no fixture (no-op — delete or add a fixture)".format(c.get("id")))
        for fid in covers:
            if fid not in fixture_ids:
                msgs.append("claim {!r} covers unknown fixture {!r}".format(c.get("id"), fid))
            covered.add(fid)
    for fid in set(fixture_ids) - covered:
        msgs.append("fixture {!r} backs no claim".format(fid))
    return (not msgs, msgs)


def _ordinal_ok(value, spec, ordinal):
    idx = {v: i for i, v in enumerate(ordinal)}
    if "equals" in spec and value != spec["equals"]:
        return False
    if "min" in spec and idx.get(value, -1) < idx.get(spec["min"], 0):
        return False
    if "max" in spec and idx.get(value, len(ordinal)) > idx.get(spec["max"], len(ordinal)):
        return False
    return True


def assert_one(output, gold, ordinal, findings_key="findings"):
    if "score" in gold:
        s, spec = output.get("score"), gold["score"]
        if not isinstance(s, int) or s < spec.get("min", 0) or s > spec.get("max", 100):
            return False
    if "level" in gold:
        if not _ordinal_ok(output.get("level"), gold["level"], ordinal):
            return False
    if "findings" in gold:
        types = {f.get("type", f.get("kind")) for f in (output.get(findings_key) or []) if f.get("evidential", True)}
        spec = gold["findings"]
        if not set(spec.get("include", [])).issubset(types):
            return False
        if types & set(spec.get("exclude", [])):
            return False
    return True


def output_assertion(trials, gold, ordinal, findings_key="findings"):
    """Probabilistic measure: fixture passes if >= 2/3 of trials meet the gold assertion."""
    n = len(trials)
    meeting = sum(1 for t in trials if assert_one(t, gold, ordinal, findings_key))
    return {"passed": n > 0 and meeting * 3 >= n * 2, "meeting": meeting, "n": n}
