#!/usr/bin/env python3
"""Combine the core verdict score with scorer-lens scores via a declared rule.

Pure: the aggregation math is the verdict's load-bearing logic, so it lives in
one unit-tested function rather than buried in orchestration prose.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))  # noqa: E402
from config import AGGREGATION_RULES  # noqa: E402


def aggregate(core, lens_scores, rule):
    """Return the final score.

    core: number. lens_scores: list of numbers from scorer lenses. rule: one of
    AGGREGATION_RULES. 'core' ignores lenses entirely; 'min' takes the lowest of
    core and all lens scores; 'mean' averages core and all lens scores.
    """
    if rule not in AGGREGATION_RULES:
        raise ValueError("unknown verdictAggregation rule: {!r}".format(rule))
    if rule == "core" or not lens_scores:
        return core
    values = [core] + list(lens_scores)
    if rule == "min":
        return min(values)
    if rule == "mean":
        return sum(values) / len(values)
    raise ValueError("unhandled rule: {!r}".format(rule))
