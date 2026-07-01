#!/usr/bin/env python3
"""Mask sensitive substrings before transcript content is published.

Pure: a single function over (text, rules). No I/O, so the no-leak guarantee
can be unit-tested in isolation and reused at every publish choke point.
"""
import re

REDACTION_MARK = "[REDACTED]"


def redact(text, rules):
    """Replace every match of each regex pattern in rules with [REDACTED].

    rules: list of regex strings. Empty rules -> text returned unchanged.
    """
    for pattern in rules:
        text = re.sub(pattern, REDACTION_MARK, text)
    return text


def redact_value(obj, rules):
    """Recursively redact string values in a JSON-like structure (dict/list/str).

    Redacting the plaintext VALUES before they are JSON- or HTML-serialized is what
    makes redaction escape-proof: a rule written for the raw secret still matches,
    because masking happens before any escaping. Dict keys are left intact (structural).
    """
    if not rules:
        return obj
    if isinstance(obj, str):
        return redact(obj, rules)
    if isinstance(obj, list):
        return [redact_value(x, rules) for x in obj]
    if isinstance(obj, dict):
        return {k: redact_value(v, rules) for k, v in obj.items()}
    return obj
