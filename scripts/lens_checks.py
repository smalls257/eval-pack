"""The five lens-evaluation checks. Pure functions over on-disk-derived inputs."""
import re

from lens_rules import check_rules

_WS = re.compile(r"\s+")


def _norm(s):
    return _WS.sub(" ", (s or "")).strip()


def evidence_resolution(output, corpus):
    """Atomic provenance: every evidential finding's quote must appear verbatim in the corpus."""
    hay = _norm(corpus)
    msgs = []
    for i, f in enumerate(output.get("findings") or []):
        if not f.get("evidential", True):
            continue
        q = _norm(f.get("quote"))
        if not q or q not in hay:
            msgs.append("finding[{}] quote unresolved: {!r}".format(i, f.get("quote")))
    return (not msgs, msgs)


def rule_consistency(output, rules, ordinal):
    """Output must satisfy the lens's own declared invariants (no ground truth)."""
    msgs = check_rules(rules, output, ordinal)
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


def assert_one(output, gold, ordinal):
    if "score" in gold:
        s, spec = output.get("score"), gold["score"]
        if not isinstance(s, int) or s < spec.get("min", 0) or s > spec.get("max", 100):
            return False
    if "level" in gold:
        if not _ordinal_ok(output.get("level"), gold["level"], ordinal):
            return False
    if "findings" in gold:
        types = {f.get("type") for f in (output.get("findings") or [])}
        spec = gold["findings"]
        if not set(spec.get("include", [])).issubset(types):
            return False
        if types & set(spec.get("exclude", [])):
            return False
    return True


def output_assertion(trials, gold, ordinal):
    """Probabilistic measure: fixture passes if >= 2/3 of trials meet the gold assertion."""
    n = len(trials)
    meeting = sum(1 for t in trials if assert_one(t, gold, ordinal))
    return {"passed": n > 0 and meeting * 3 >= n * 2, "meeting": meeting, "n": n}
