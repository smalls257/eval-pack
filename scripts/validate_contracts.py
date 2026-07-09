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


def _read_config(pack_dir):
    """Missing config -> DEFAULTS (pipeline guarantees presence; standalone runs stay usable).
    Present-but-unparseable -> DEFAULTS plus an explicit gap: corruption must not validate silently."""
    p = Path(pack_dir) / "eval-config.json"
    if not p.is_file():
        return config.read_config(), None
    try:
        return json.loads(p.read_text(encoding="utf-8")), None
    except json.JSONDecodeError as exc:
        return config.read_config(), "eval-config.json present but unparseable ({})".format(exc)


def _friction_gaps(cfg, analysis):
    gaps = []
    cats = set(cfg.get("frictionCategories") or [])
    if not cats:
        return gaps
    for i, item in enumerate(analysis.get("frictionLog") or []):
        t = item.get("type")
        if t not in cats:
            gaps.append("frictionLog[{}].type {!r} is not in frictionCategories {}".format(
                i, t, sorted(cats)))
    return gaps


def _retrospective_gaps(cfg, analysis):
    gaps = []
    questions = cfg.get("retrospectiveQuestions") or []
    if not questions:
        return gaps
    answered = {a.get("question") for a in analysis.get("retrospectiveAnswers") or []
                if a.get("answer")}
    for q in questions:
        if q not in answered:
            gaps.append("retrospectiveAnswers missing or blank answer for: {!r}".format(q))
    return gaps


def _rubric_gaps(cfg, analysis):
    gaps = []
    rubric = cfg.get("rubric") or {}
    if not rubric:
        return gaps
    applied = analysis.get("rubricApplied") or {}
    band = applied.get("band")
    if not band:
        gaps.append("rubricApplied missing: config sets a rubric but analysis names no band")
    elif band not in rubric:
        gaps.append("rubricApplied.band {!r} is not a configured rubric band {}".format(
            band, sorted(rubric)))
    return gaps


def _command_gaps(cfg, results):
    gaps = []
    commands = cfg.get("testCommands") or []
    if not commands:
        return gaps
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


def collect_gaps(pack_dir):
    """Return a list of human-readable contract violations; empty means conforming."""
    gaps = []
    cfg, cfg_gap = _read_config(pack_dir)
    if cfg_gap:
        gaps.append(cfg_gap)
    analysis = _read(pack_dir, "analysis.json") or {}
    results = _read(pack_dir, "test-results.json") or {}

    if not analysis.get("disabled"):
        gaps.extend(_friction_gaps(cfg, analysis))
        gaps.extend(_retrospective_gaps(cfg, analysis))
        gaps.extend(_rubric_gaps(cfg, analysis))
    gaps.extend(_command_gaps(cfg, results))
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
