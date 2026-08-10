#!/usr/bin/env python3
"""Assemble per-lens outputs into lenses.json and compute the aggregated verdict score.

Each configured lens (dispatched as a subagent by the generate skill) writes one file
`PACK_DIR/lenses/<id>.json`. This script collects them, reads the core confidence from
analysis.json and the aggregation rule from eval-config.json, and writes `PACK_DIR/lenses.json`
with contributors, scorers, failures, and the transparent aggregation math (Guard G2). Keeping
the aggregation in a tested script — not orchestration prose — makes the verdict auditable.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))  # noqa: E402
import aggregate  # noqa: E402
import config  # noqa: E402
import lens_versions  # noqa: E402
import lens_manifest  # noqa: E402
import lens_contract  # noqa: E402


def validate_lens_contracts(results):
    """A lens whose .md declares an output contract must satisfy it; a violation is a failure.
    Lenses with no declared contract (or no .md on disk) pass through unchanged."""
    validated = []
    for r in results:
        if "error" in r:
            validated.append(r)
            continue
        md_path = lens_versions.LENS_DIR / (r.get("skill", "") + ".md")
        contract = None
        if md_path.is_file():
            contract = lens_manifest.find_output_contract(md_path.read_text(encoding="utf-8"))
        if contract is None:
            validated.append(r)
            continue
        violations = lens_contract.validate_output(r, contract)
        if violations:
            validated.append({"skill": r.get("skill"), "role": r.get("role", "unknown"),
                              "error": "contract violation: " + "; ".join(violations)})
        else:
            validated.append(r)
    return validated


def assemble(pack_dir):
    pack = Path(pack_dir)
    lens_dir = pack / "lenses"
    results = []
    if lens_dir.is_dir():
        for f in sorted(lens_dir.glob("*.json")):
            try:
                r = json.loads(f.read_text(encoding="utf-8"))
                r.setdefault("skill", f.stem)
                results.append(r)
            except (json.JSONDecodeError, OSError):
                results.append({"skill": f.stem, "role": "unknown",
                                "error": "malformed or unreadable lens output"})

    results = validate_lens_contracts(results)

    cfg_path = pack / "eval-config.json"
    cfg = config.read_config(str(cfg_path)) if cfg_path.is_file() else config.read_config()
    rule = cfg.get("verdictAggregation", "core")

    # Orphan guard: the pack dir persists across rounds (render no longer deletes it), so a
    # lenses/<skill>.json from a lens since removed from config could linger. Assemble only what
    # is CONFIGURED — a present-but-unconfigured file is ignored (the reverse of the vanishing-lens
    # gate below, which flags configured-but-missing).
    configured = {l.get("skill") for l in cfg.get("analysisLenses") or [] if l.get("skill")}
    results = [r for r in results if r.get("skill") in configured]

    # Deterministic gate: a configured lens with no output file is a FAILURE, not an absence.
    # The orchestrator is an LLM; prose promises don't count. (finding: vanishing lens)
    produced = {r.get("skill") for r in results}
    for lens in cfg.get("analysisLenses") or []:
        skill = lens.get("skill")
        if skill and skill not in produced:
            results.append({"skill": skill, "role": lens.get("role", "unknown"),
                            "error": "configured lens produced no output"})

    def _ok(r):
        return "error" not in r

    contributors = [r for r in results if r.get("role") == "contributor" and _ok(r)]
    scorers = [r for r in results if r.get("role") == "scorer" and _ok(r)
               and isinstance(r.get("score"), (int, float)) and not isinstance(r.get("score"), bool)]
    # A scorer that ran but returned a non-numeric score is a failure, not silently dropped.
    failures = [r for r in results if not _ok(r)
                or (r.get("role") == "scorer" and r not in scorers)]

    # Attach each lens's repo-authored template markup (embedded at resolve time) to its
    # result so the renderer can use it; failures keep the default (visible) rendering.
    # Provenance is enforced structurally: templateHtml on a lens result is trusted (the
    # renderer feeds it to safe() as raw HTML), so it may ONLY come from the confined
    # config embedding. A lens's lenses/<skill>.json is LLM-authored (untrusted); strip any
    # self-declared templateHtml BEFORE re-attaching the confined one, or that markup would
    # be rendered as trusted — a stored XSS (finding: trust inversion, security review).
    tpl_by_skill = {l.get("skill"): l.get("templateHtml")
                    for l in cfg.get("analysisLenses") or [] if l.get("templateHtml")}
    # display is presentation config, not lens output — same trust rule as templateHtml:
    # a lens's self-declared display is untrusted and stripped; the configured value wins.
    disp_by_skill = {l.get("skill"): l.get("display")
                     for l in cfg.get("analysisLenses") or [] if l.get("display")}
    # cardStyle ('hero'|'list') is presentation config — same trust rule as display: a lens's
    # self-declared cardStyle is untrusted and stripped; the config value wins.
    cardstyle_by_skill = {l.get("skill"): l.get("cardStyle")
                          for l in cfg.get("analysisLenses") or [] if l.get("cardStyle")}
    # version is lens metadata — config/lockfile-sourced, same trust rule as display/templateHtml:
    # a lens's self-declared version is untrusted and stripped; the configured/locked value wins.
    _lock = lens_versions.load_lock()
    ver_by_skill = {l.get("skill"): l.get("version")
                    for l in cfg.get("analysisLenses") or [] if l.get("version")}
    for r in results:
        r.pop("templateHtml", None)  # never trust lens-supplied markup — resolve-embedded only
        r.pop("display", None)       # never trust lens-supplied presentation — config only
        r.pop("cardStyle", None)     # never trust lens-supplied presentation — config only
        r.pop("version", None)       # never trust lens-supplied version — config/lockfile only
        t = tpl_by_skill.get(r.get("skill"))
        if t and "error" not in r:
            r["templateHtml"] = t
        d = disp_by_skill.get(r.get("skill"))
        if d and "error" not in r:
            r["display"] = d
        cs = cardstyle_by_skill.get(r.get("skill"))
        if cs and "error" not in r:
            r["cardStyle"] = cs
        # version attaches to failures too — it's metadata, not trusted markup; a failure card
        # should show which lens version failed. So no "error not in r" guard here.
        v = ver_by_skill.get(r.get("skill")) or (_lock.get(r.get("skill")) or {}).get("version")
        if v:
            r["version"] = v

    analysis_path = pack / "analysis.json"
    analysis = {}
    if analysis_path.is_file():
        try:
            analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            analysis = {}
    core = (analysis.get("highlights") or {}).get("confidencePercent")

    out = {"rule": rule, "contributors": contributors, "scorers": scorers, "failures": failures}
    if isinstance(core, (int, float)) and not isinstance(core, bool):
        out["coreScore"] = core
        if scorers:
            try:
                out["finalScore"] = aggregate.aggregate(core, [s["score"] for s in scorers], rule)
            except ValueError as exc:
                out["aggregationError"] = str(exc)
    return out


def _lens_flags(out, sev):
    """Deterministic flags for the verdict banner (rides the tested patterns pipeline).

    lensFailed is intentionally NOT suppressible via flagSeverities: it is the
    can't-vanish gate for configured lenses — a config that could turn it off would
    recreate the silent-vanishing hole it exists to close. lensVerdict honors the
    user's flagSeverities retune like every other flag id.
    """
    flags = []
    for f in out.get("failures", []):
        flags.append({"id": "lensFailed", "level": "red",
                      "label": "Lens failed: {} ({})".format(
                          f.get("skill", "?"), f.get("error", "error"))})
    core, final = out.get("coreScore"), out.get("finalScore")
    if final is not None and core is not None and final < core:
        level = sev.get("lensVerdict", "amber")
        if level != "off":
            flags.append({"id": "lensVerdict", "level": level,
                          "label": "Lens verdict: final {:g} ({} of core {:g} and {} scorer(s))".format(
                              final, out.get("rule"), core, len(out.get("scorers", [])))})
    return flags


def write_outputs(pack_dir, out):
    """Write lenses.json and append lens flags into patterns.json (never crash the eval)."""
    pack = Path(pack_dir)
    (pack / "lenses.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    cfg_path = pack / "eval-config.json"
    cfg = config.read_config(str(cfg_path)) if cfg_path.is_file() else config.read_config()
    new_flags = _lens_flags(out, cfg.get("flagSeverities") or {})
    if not new_flags:
        return
    ppath = pack / "patterns.json"
    try:
        patterns = json.loads(ppath.read_text(encoding="utf-8")) if ppath.is_file() else {"flags": []}
    except json.JSONDecodeError as exc:
        print(
            "Warning: patterns.json was unreadable ({}) — heuristic flags lost; "
            "writing lens flags only".format(exc),
            file=sys.stderr,
        )
        patterns = {"flags": []}
    existing = patterns.setdefault("flags", [])
    # idempotent on re-run: drop prior lens flags before appending
    patterns["flags"] = [f for f in existing if f.get("id") not in ("lensFailed", "lensVerdict")] + new_flags
    ppath.write_text(json.dumps(patterns, indent=2), encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Assemble lens outputs into lenses.json")
    parser.add_argument("pack_dir")
    args = parser.parse_args(argv)
    out = assemble(args.pack_dir)
    write_outputs(args.pack_dir, out)
    print("lenses.json: {} contributors, {} scorers, {} failures".format(
        len(out["contributors"]), len(out["scorers"]), len(out["failures"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
