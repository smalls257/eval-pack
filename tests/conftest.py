"""Pytest collection guard for lens-evaluator fixtures.

Committed eval bundles under tests/lenses/<lens>/fixtures/<case>/ are DATA, not tests.
Some carry a reconstructed repo under base/ that legitimately contains test_*.py source
files (e.g. a project's own test suite at the base commit). Pytest must not try to
collect those as test modules — they import packages that aren't installed here and would
raise collection errors. Ignore everything under any fixture directory.
"""

collect_ignore_glob = [
    "lenses/*/fixtures/*",
    "lenses/*/fixtures/*/*",
    "lenses/*/fixtures/*/**",
]
