"""Closed-grammar evaluator for a lens's self-declared output invariants. Pure, fail-loud."""

_FIELDS = {"level", "score", "findings.types"}
_REQUIRE_OPS = {"subset_of", "at_least_one_in", "equals", "min", "max"}


def _finding_types(output):
    return [f.get("type") for f in (output.get("findings") or [])]


def _field_value(field, output):
    if field == "findings.types":
        return _finding_types(output)
    if field in ("level", "score"):
        return output.get(field)
    raise ValueError("unknown rule field: {!r}".format(field))


def _cmp_ok(spec, value, ordinal):
    """spec is a bare value (exact match) or {min|max|equals: v}."""
    if not isinstance(spec, dict):
        return value == spec
    for op, target in spec.items():
        if op == "equals":
            if value != target:
                return False
        elif op in ("min", "max"):
            if value in ordinal and target in ordinal:
                lo, hi = ordinal.index(value), ordinal.index(target)
                if op == "min" and lo < hi:
                    return False
                if op == "max" and lo > hi:
                    return False
            else:  # numeric
                if op == "min" and value < target:
                    return False
                if op == "max" and value > target:
                    return False
        else:
            raise ValueError("unknown when-operator: {!r}".format(op))
    return True


def _when_matches(when, output, ordinal):
    for field, spec in when.items():
        if field not in _FIELDS:
            raise ValueError("unknown rule field: {!r}".format(field))
        if not _cmp_ok(spec, _field_value(field, output), ordinal):
            return False
    return True


def _require_ok(require, output, ordinal):
    msgs = []
    for field, spec in require.items():
        if field not in _FIELDS:
            raise ValueError("unknown rule field: {!r}".format(field))
        value = _field_value(field, output)
        if not isinstance(spec, dict):
            raise ValueError("require-clause for {!r} must be an operator dict, got {!r}".format(field, spec))
        for op, target in spec.items():
            if op not in _REQUIRE_OPS:
                raise ValueError("unknown require-operator: {!r}".format(op))
            types = set(value if isinstance(value, list) else [value])
            if op == "subset_of" and not types.issubset(set(target)):
                msgs.append("{} {} not subset_of {}".format(field, sorted(types), target))
            elif op == "at_least_one_in" and types.isdisjoint(set(target)):
                msgs.append("{} has none of {}".format(field, target))
            elif op in ("equals", "min", "max") and not _cmp_ok({op: target}, value, ordinal):
                msgs.append("{} fails {} {}".format(field, op, target))
    return msgs


def check_rules(rules, output, ordinal):
    violations = []
    for r in rules:
        if _when_matches(r.get("when", {}), output, ordinal):
            violations += _require_ok(r.get("require", {}), output, ordinal)
    return violations
