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
from discover_repos import canon_root, discover_write_repos  # noqa: E402


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


def _friction_gaps(cfg, pack_dir):
    """Check the friction LENS output (lenses/friction.json), not analysis.json.

    The friction dimension was extracted from the evaluator into a default-on
    'friction' contributor lens (lens-decomposition Task 3); its data now lives under
    PACK_DIR/lenses/, assembled by the lens step that runs BEFORE the evaluator (so the
    evaluator can ingest lens findings — the pipeline order is lenses -> evaluator ->
    this gate -> render). This function reads whatever is on disk at gate time and
    doesn't care which step wrote it or when; an absent lens file is NOT a taxonomy gap
    here regardless — a configured-but-missing lens is already a non-suppressible
    'lensFailed' red flag from assemble_lenses.py, so gating it again here would be a
    duplicate, confusing signal for the same root cause (Silent Fallback in reverse:
    don't manufacture a second failure mode for one absence).

    The file is LLM-authored, so every access is type-guarded: a non-dict payload,
    non-list `entries`, or non-dict entry each yields a deterministic GAP, never an
    exception. render_html's collect_gaps call has no try/except, so a raw AttributeError
    here would kill the render gate with a traceback and NO 'CONTRACT:' line — a Black Box
    where a clean, attributable gate is the whole point.
    """
    cats = set(cfg.get("frictionCategories") or [])
    if not cats:
        return []
    friction = _read(pack_dir, "lenses/friction.json")
    if friction is None:
        return []  # absent lens is a legitimate no-op (see docstring)
    if not isinstance(friction, dict):
        return ["lenses/friction.json is malformed (expected an object with 'entries')"]
    entries = friction.get("entries")
    if entries is None:
        return []
    if not isinstance(entries, list):
        return ["lenses/friction.json 'entries' must be a list"]
    gaps = []
    for item in entries:
        if not isinstance(item, dict):
            gaps.append("lenses/friction.json entry is not an object")
            continue
        t = item.get("type")
        if t not in cats:
            gaps.append("friction entry type {!r} not in frictionCategories {}".format(
                t, sorted(cats)))
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
    slash; on Windows, forward vs back slashes or a case difference — Windows filesystems
    are case-insensitive). Comparing raw strings would report a genuinely-covered repo as
    unaccounted and refuse a CORRECT pack — a Silent Fallback where a path-form artifact
    masquerades as missing coverage. Delegates to discover_repos.canon_root — THE single
    canonicalization chokepoint — so this module's notion of "same repo" never drifts
    from repo_diffs.py's.
    """
    return canon_root(p)


def _repo_coverage_gaps(pack_dir):
    """Deterministic, non-skippable multi-repo coverage backstop.

    Re-derives which repos the session WROTE to from the pack's own transcript
    (ground truth), NOT from the skill-written discovered-repos.json — so a skill
    run that skipped the discovery step cannot silently pass a multi-repo session
    as a single-repo eval (Sensor: the change surface's boundary is observed at
    render time, not assumed to have been observed upstream).

    Fires only when the session wrote to >= 2 repos (the multi-repo case). A
    single write-touched repo is the ordinary case the legacy single-diff flow
    already covers, so it is not gated here (backward compatible).
    """
    tpath = Path(pack_dir) / "transcript.jsonl"
    if not tpath.is_file():
        return []   # no transcript to derive from (should not happen at real render)

    # Resolve git for ONLY the write-touched dirs — the gate consults nothing else, and
    # full discover() would shell ~4 git calls per DISTINCT dir referenced anywhere in the
    # transcript (read/cwd/cd included), thousands on a big session (Engine: don't pay for
    # resolution the gate never reads). Behavior is identical to the old discover()+"write"
    # filter for the write-repo subset — same repoRoot/branch/signals keys.
    write_repos = discover_write_repos(str(tpath))
    if len(write_repos) < 2:
        return []   # single/zero write-touched repo: legacy single-diff flow covers it

    diffs = _read(pack_dir, "repo-diffs.json")
    if diffs is None:
        roots = ", ".join(r.get("repoRoot") for r in write_repos)
        return ["session wrote to {} repos but repo-diffs.json is missing — run the "
                "multi-repo discovery/diff step (repos: {})".format(len(write_repos), roots)]

    accounted = {_canon_root(r.get("repoRoot")) for r in diffs.get("repos") or []}
    accounted |= {_canon_root(s.get("repoRoot")) for s in diffs.get("skipped") or []}

    gaps = []
    for r in write_repos:
        if _canon_root(r.get("repoRoot")) not in accounted:
            gaps.append("repo written to but neither evaluated nor skipped: {} (branch {}) "
                        "— resolve or skip it".format(r.get("repoRoot"), r.get("branch")))
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

    # retrospective/rubric are EVALUATOR-owned — they only exist when analysis ran, so
    # they stay behind the `disabled` guard. friction is LENS-owned: Step 4.7 dispatches
    # analysisLenses independently of analysis:false, so the friction lens (and a bad
    # taxonomy) can exist even with analysis disabled — its gate must run unconditionally,
    # alongside the command and repo-coverage gates, or a bad type ships un-gated.
    if not analysis.get("disabled"):
        gaps.extend(_retrospective_gaps(cfg, analysis))
        gaps.extend(_rubric_gaps(cfg, analysis))
    gaps.extend(_friction_gaps(cfg, pack_dir))
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
