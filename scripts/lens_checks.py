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
