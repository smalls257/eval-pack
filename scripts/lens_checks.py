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
