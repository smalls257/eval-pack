#!/usr/bin/env python3
"""Deterministic contract gates for LLM-produced pack artifacts.

Principle: we don't trust LLMs — we trust validation. The evaluator and the
orchestrating skill PROMISE to honor the resolved config (friction taxonomy,
retrospective questions, rubric, test commands); this script CHECKS. A violation
is a gap that halts the pipeline (the skill re-dispatches once, then stops), and
render_html refuses to render a non-conforming pack as the code-level backstop.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))  # noqa: E402
import config  # noqa: E402


def _read(pack, name):
    p = Path(pack) / name
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def collect_gaps(pack_dir):
    """Return a list of human-readable contract violations; empty means conforming."""
    gaps = []
    cfg_data = _read(pack_dir, "eval-config.json")
    cfg = cfg_data if cfg_data is not None else config.read_config()
    analysis = _read(pack_dir, "analysis.json") or {}
    results = _read(pack_dir, "test-results.json") or {}

    if not analysis.get("disabled"):
        # frictionLog types must come from the configured taxonomy.
        cats = set(cfg.get("frictionCategories") or [])
        if cats:
            for i, item in enumerate(analysis.get("frictionLog") or []):
                t = item.get("type")
                if t not in cats:
                    gaps.append(
                        "frictionLog[{}].type {!r} is not in frictionCategories {}".format(
                            i, t, sorted(cats)))
        # every configured retrospective question must be answered, verbatim-keyed.
        questions = cfg.get("retrospectiveQuestions") or []
        if questions:
            answered = {a.get("question") for a in analysis.get("retrospectiveAnswers") or []
                        if a.get("answer")}
            for q in questions:
                if q not in answered:
                    gaps.append("retrospectiveAnswers missing an answer for: {!r}".format(q))
        # a configured rubric must be applied to a real band.
        rubric = cfg.get("rubric") or {}
        if rubric:
            applied = analysis.get("rubricApplied") or {}
            band = applied.get("band")
            if not band:
                gaps.append("rubricApplied missing: config sets a rubric but analysis names no band")
            elif band not in rubric:
                gaps.append("rubricApplied.band {!r} is not a configured rubric band {}".format(
                    band, sorted(rubric)))

    # configured test commands must be proven run, with a consistent verdict.
    commands = cfg.get("testCommands") or []
    if commands:
        ran = {c.get("command"): c.get("exitCode") for c in results.get("commands") or []}
        for cmd in commands:
            if cmd not in ran:
                gaps.append("test-results.commands missing configured command: {!r}".format(cmd))
        exit_codes = [ran[c] for c in commands if c in ran]
        if exit_codes and len(exit_codes) == len(commands):
            expected = "pass" if all(x == 0 for x in exit_codes) else "fail"
            if results.get("verdict") != expected:
                gaps.append("test-results.verdict {!r} inconsistent with exit codes {} "
                            "(expected {!r})".format(results.get("verdict"), exit_codes, expected))
    return gaps


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate pack artifacts against the resolved config")
    parser.add_argument("pack_dir")
    args = parser.parse_args(argv)
    gaps = collect_gaps(args.pack_dir)
    for g in gaps:
        print("CONTRACT: " + g, file=sys.stderr)
    print("contracts: {} violation(s)".format(len(gaps)))
    return 1 if gaps else 0


if __name__ == "__main__":
    sys.exit(main())
