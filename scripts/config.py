#!/usr/bin/env python3
"""Resolve eval-pack configuration from layered sources.

Precedence (low -> high):
  DEFAULTS < extends presets < .eval-pack.json < .eval-pack.local.json < CLAUDE_PLUGIN_OPTION_*
Pure: reads files and env only. No network, no clock — unit-testable in isolation.
"""
import json
import os
import re
from pathlib import Path


class ConfigError(Exception):
    """Raised when config input is malformed: bad JSON or an uncoercible env value."""

# Defaults preserve today's hardcoded behavior. Override nothing -> identical output.
DEFAULTS = {
    # Scope drift: monorepo PRs typically touch <10 files; beyond this suggests task bleed.
    "scopeDriftFileThreshold": 10,
    # Retry amber flag: 4+ retries indicates repeated misunderstanding, not course-correction.
    "retryAmberThreshold": 4,
    # Skill args truncation: keeps tools.json readable without losing functional context.
    "skillArgsMaxLen": 200,
    # Friction taxonomy the evaluator must classify into (consumed by a later layer).
    "frictionCategories": ["tooling", "structure", "naming", "docs", "other"],
    # Commands the generate skill runs to determine the test verdict (consumed by a later layer).
    "testCommands": [],
    # Ticket-key regex for PR-body linking (consumed by a later layer).
    "ticketPattern": r"[A-Z][A-Z0-9]+-[0-9]+",
    # Regex patterns whose matches are masked in published transcripts (security).
    "redaction": [],
    # Whether to write an openable (unzipped) copy of the pack to a temp dir.
    "publishOpenable": True,
    # Directory for the openable copy; empty means the system temp dir.
    "openableDir": "",
    # Named evaluator persona preset (file under presets/stances/<name>.md).
    "analysisStance": "skeptical-reviewer",
    # Structured scoring rubric (band -> criteria); empty uses the built-in anchor.
    "rubric": {},
    # Retrospective questions for the evaluator; empty uses the built-in set.
    "retrospectiveQuestions": [],
    # Path to an override evaluator prompt; empty uses the bundled default.
    "evaluatorPromptFile": "",
    # Extension lenses: list of {"skill": str, "role": "contributor"|"scorer"}.
    "analysisLenses": [],
    # How scorer-lens scores combine with the core verdict (see AGGREGATION_RULES).
    "verdictAggregation": "core",
    # Presentation. Defaults preserve today's look (brand "Eval Pack", dark theme, "extension").
    "brandName": "Eval Pack",
    "reportTitle": "",
    "footerText": "",
    "subjectNoun": "extension",
    "defaultTheme": "dark",
    "sections": [],
    "zipNameTemplate": "",
    "commitUrlTemplate": "",
    "repoBaseUrl": "",
    "messages": {},
}

# Known keys and their expected JSON/Python types. A key absent here is "unknown"
# (the runtime equivalent of JSON Schema additionalProperties:false).
_TYPES = {
    "scopeDriftFileThreshold": int,
    "retryAmberThreshold": int,
    "skillArgsMaxLen": int,
    "frictionCategories": list,
    "testCommands": list,
    "ticketPattern": str,
    "redaction": list,
    "publishOpenable": bool,
    "openableDir": str,
    "analysisStance": str,
    "rubric": dict,
    "retrospectiveQuestions": list,
    "evaluatorPromptFile": str,
    "analysisLenses": list,
    "verdictAggregation": str,
    "brandName": str,
    "reportTitle": str,
    "footerText": str,
    "subjectNoun": str,
    "defaultTheme": str,
    "sections": list,
    "zipNameTemplate": str,
    "commitUrlTemplate": str,
    "repoBaseUrl": str,
    "messages": dict,
}

# Keys consumed during merge or by editors only — never part of the resolved config.
_META_KEYS = {"extends", "$schema"}

# Allowed verdict aggregation rules (shared with scripts/aggregate.py).
AGGREGATION_RULES = ("core", "min", "mean")

# Allowed report themes.
THEMES = ("dark", "light", "system")


def _read_json(path):
    p = Path(path)
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError("{}: invalid JSON ({})".format(p.name, exc)) from exc


def _dedupe(seq):
    out = []
    for x in seq:
        if x not in out:
            out.append(x)
    return out


def _strip_meta(d):
    return {k: v for k, v in d.items() if k not in _META_KEYS}


def _overlay(base, layer):
    for k, v in layer.items():
        if isinstance(v, list) and isinstance(base.get(k), list):
            base[k] = _dedupe(base[k] + v)
        else:
            base[k] = v
    return base


def _copy_default(v):
    # Copy mutable containers so a returned config can never mutate DEFAULTS.
    if isinstance(v, list):
        return list(v)
    if isinstance(v, dict):
        return dict(v)
    return v


def _fresh_defaults():
    return {k: _copy_default(v) for k, v in DEFAULTS.items()}


def _coerce(raw, typ, key):
    if typ is bool:
        low = raw.strip().lower()
        if low in ("1", "true", "yes", "on"):
            return True
        if low in ("0", "false", "no", "off"):
            return False
        raise ConfigError(
            "CLAUDE_PLUGIN_OPTION_{}: expected a boolean, got {!r}".format(key, raw)
        )
    if typ is int:
        try:
            return int(raw)
        except ValueError as exc:
            raise ConfigError(
                "CLAUDE_PLUGIN_OPTION_{}: expected int, got {!r}".format(key, raw)
            ) from exc
    if typ is list:
        # Dedupe to match the file-layer list-merge semantics (consistency).
        return _dedupe([s for s in raw.split(",") if s])
    return raw


def _apply_env(cfg, env):
    for key, typ in _TYPES.items():
        raw = env.get("CLAUDE_PLUGIN_OPTION_" + key)
        if raw not in (None, ""):
            cfg[key] = _coerce(raw, typ, key)
    return cfg


def load_config(project_root, env=None):
    """Return the merged, resolved config dict. Does NOT validate (call validate()).

    List merge differs by layer: file layers (presets, .eval-pack.json,
    .eval-pack.local.json) concat-then-dedupe onto the base, but a
    CLAUDE_PLUGIN_OPTION_* env override REPLACES the list outright. Raises
    ConfigError on malformed JSON or an uncoercible env value.
    """
    env = os.environ if env is None else env
    root = Path(project_root)
    project_cfg = _read_json(root / ".eval-pack.json")
    local_cfg = _read_json(root / ".eval-pack.local.json")

    merged = _fresh_defaults()
    # extends is single-level and project-only: presets cannot themselves extend.
    for preset_id in project_cfg.get("extends", []):
        preset_path = root / preset_id
        if not preset_path.is_file():
            # Fail loud: a typo'd/renamed preset must not silently resolve to defaults.
            raise ConfigError("extends: preset not found: {}".format(preset_id))
        _overlay(merged, _strip_meta(_read_json(preset_path)))
    _overlay(merged, _strip_meta(project_cfg))
    _overlay(merged, _strip_meta(local_cfg))
    _apply_env(merged, env)
    return merged


def validate(cfg):
    """Return a list of human-readable error strings; empty list means valid."""
    errors = []
    for k, v in cfg.items():
        if k not in _TYPES:
            errors.append("unknown config key: {!r}".format(k))
            continue
        typ = _TYPES[k]
        if typ is int and isinstance(v, bool):
            errors.append("{}: expected int, got bool".format(k))
        elif not isinstance(v, typ):
            errors.append("{}: expected {}, got {}".format(k, typ.__name__, type(v).__name__))
    rules = cfg.get("redaction")
    if isinstance(rules, list):
        for pat in rules:
            try:
                re.compile(pat)
            except re.error as exc:
                errors.append("redaction: invalid regex {!r} ({})".format(pat, exc))
    rule = cfg.get("verdictAggregation")
    if rule is not None and rule not in AGGREGATION_RULES:
        errors.append(
            "verdictAggregation: {!r} is not one of {}".format(rule, list(AGGREGATION_RULES))
        )
    lenses = cfg.get("analysisLenses")
    if isinstance(lenses, list):
        for i, lens in enumerate(lenses):
            if not isinstance(lens, dict) or "skill" not in lens:
                errors.append("analysisLenses[{}]: must be an object with a 'skill'".format(i))
            elif lens.get("role") not in ("contributor", "scorer"):
                errors.append(
                    "analysisLenses[{}]: role must be 'contributor' or 'scorer'".format(i)
                )
    theme = cfg.get("defaultTheme")
    if theme is not None and theme not in THEMES:
        errors.append("defaultTheme: {!r} is not one of {}".format(theme, list(THEMES)))
    # Non-negative bound: a negative truncation length is a garbage (negative-index) slice.
    n = cfg.get("skillArgsMaxLen")
    if isinstance(n, int) and not isinstance(n, bool) and n < 0:
        errors.append("skillArgsMaxLen: must be >= 0, got {}".format(n))
    return errors


def read_config(path=None):
    """Read an already-resolved eval-config.json, or fresh DEFAULTS when path is None.

    Used by scripts so they run standalone (no --config) with default behavior.
    """
    if path:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    return _fresh_defaults()
