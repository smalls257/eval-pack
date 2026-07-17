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
import os
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


def _canon_root(p):
    """Canonicalize a repo root for comparison: resolve symlinks, drop trailing slash.

    The two sides of the coverage match normalize differently — discovered-repos.json
    holds git's `--show-toplevel` (symlink-resolved, canonical) while a naive selection
    could echo a raw string (e.g. /var/... vs /private/var/... on macOS, or a trailing
    slash). Comparing raw strings would report a genuinely-covered repo as unaccounted
    and refuse a CORRECT pack — a Silent Fallback where a path-form artifact masquerades
    as missing coverage. Canonicalizing both sides makes the match reflect repo identity,
    not string form. realpath still normalizes lexically for a nonexistent path.
    """
    return os.path.realpath(p).rstrip("/") if p else p


def _repo_coverage_gaps(pack_dir):
    """Multi-repo coverage backstop.

    discover_repos.py finds every repo/worktree a session touched; repo_diffs.py
    records what the user chose to evaluate or skip. A repo that was touched but
    left in neither bucket would let the evaluator silently score just one repo
    of a multi-repo session (Sensor: the change surface's boundary must be
    observable and complete, not assumed). This is opt-in: packs with no
    discovered-repos.json — or an empty discovery (a non-git session, or the
    feature engaged but found nothing) — are legacy and conform trivially.
    """
    discovered = _read(pack_dir, "discovered-repos.json")
    if not discovered:
        return []

    diffs = _read(pack_dir, "repo-diffs.json")
    if diffs is None:
        return ["repos discovered but none evaluated — run repo_diffs.py (repo-diffs.json missing)"]

    accounted = {_canon_root(r.get("repoRoot")) for r in diffs.get("repos") or []}
    accounted |= {_canon_root(s.get("repoRoot")) for s in diffs.get("skipped") or []}

    gaps = []
    for repo in discovered:
        root = repo.get("repoRoot")
        if _canon_root(root) not in accounted:
            gaps.append(
                "repo touched but neither evaluated nor skipped: {} (branch {}) — "
                "resolve or skip it".format(root, repo.get("branch")))

    for err in diffs.get("errors") or []:
        gaps.append("repo diff failed for {}: {} — fix the base ref or skip the repo".format(
            err.get("repoRoot"), err.get("error")))

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
    gaps.extend(_repo_coverage_gaps(pack_dir))
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
