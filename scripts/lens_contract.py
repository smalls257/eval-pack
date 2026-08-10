"""Validate a lens output dict against its declared output contract. Pure, stdlib."""


def validate_output(output, contract):
    v = []
    gf = contract.get("gradedField")
    if gf == "score":
        s = output.get("score")
        if not isinstance(s, int) or isinstance(s, bool) or not (0 <= s <= 100):
            v.append("score must be int 0-100, got {!r}".format(s))
    elif gf == "level":
        ordinal = contract.get("levelOrdinal") or []
        if output.get("level") not in ordinal:
            v.append("level {!r} not in {}".format(output.get("level"), ordinal))
    elif gf == "none":
        pass
    else:
        v.append("contract gradedField invalid: {!r}".format(gf))

    if "findingTypes" in contract:
        allowed = set(contract.get("findingTypes") or [])
        fkey = contract.get("findingsKey", "findings")
        tfield = contract.get("typeField", "type")
        for i, f in enumerate(output.get(fkey) or []):
            if f.get(tfield) not in allowed:
                v.append("{}[{}] {} {!r} not in {}".format(fkey, i, tfield, f.get(tfield), sorted(allowed)))
            if f.get("evidential", True) and not (f.get("quote") or "").strip():
                v.append("{}[{}] is evidential but has no quote".format(fkey, i))
    return v
