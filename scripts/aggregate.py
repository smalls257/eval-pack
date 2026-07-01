#!/usr/bin/env python3
"""Combine the core verdict score with scorer-lens scores via a declared rule.

Pure: the aggregation math is the verdict's load-bearing logic, so it lives in
one unit-tested function rather than buried in orchestration prose.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))  # noqa: E402
from config import AGGREGATION_RULES  # noqa: E402


def _clamp_score(x):
    """Return x as a float in [0, 100], or None if it isn't a usable number.

    A lens is an external skill; its score is untrusted. Out-of-range values are
    clamped, and non-numeric / NaN values are rejected so garbage never reaches the
    verdict panel.
    """
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if v != v:  # NaN
        return None
    return max(0.0, min(100.0, v))


def aggregate(core, lens_scores, rule):
    """Return the final score.

    core: number. lens_scores: scorer-lens scores (sanitized: non-numeric dropped,
    others clamped to [0,100]). rule: one of AGGREGATION_RULES. 'core' ignores lenses;
    'min' takes the lowest of core and all lens scores; 'mean' averages them.
    """
    if rule not in AGGREGATION_RULES:
        raise ValueError("unknown verdictAggregation rule: {!r}".format(rule))
    c = _clamp_score(core)
    if c is None:
        raise ValueError("core score is not a number: {!r}".format(core))
    # A malformed scorer score is dropped, not crashed on — it simply can't move the verdict.
    scores = [s for s in (_clamp_score(x) for x in lens_scores) if s is not None]
    if rule == "core" or not scores:
        return c
    values = [c] + scores
    if rule == "min":
        return min(values)
    if rule == "mean":
        return sum(values) / len(values)
    raise ValueError("unhandled rule: {!r}".format(rule))
