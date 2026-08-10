"""Build a provenance ledger from a lens basis's sources. Pure over an injected resolver;
network resolution (arXiv/DOI) lives in the CLI shell, not imported by the gate. Stdlib only."""


def build_ledger(sources, resolve):
    ledger = {}
    for s in sources:
        meta = resolve(s.get("citation"))
        ledger[s["id"]] = {"title": meta.get("title"), "authors": meta.get("authors"),
                           "date": meta.get("date"), "resolved_at": None}
    return ledger
