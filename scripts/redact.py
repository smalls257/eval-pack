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
