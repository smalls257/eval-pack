#!/usr/bin/env python3
"""Resolve eval-pack configuration from layered sources.

Precedence (low -> high):
  DEFAULTS < extends presets < .eval-pack.json < .eval-pack.local.json < CLAUDE_PLUGIN_OPTION_*
Pure: reads files and env only. No network, no clock — unit-testable in isolation.
"""
import json
import os
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
}

# Keys consumed during merge or by editors only — never part of the resolved config.
_META_KEYS = {"extends", "$schema"}


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


def _fresh_defaults():
    # Copy list values so a returned config can never mutate DEFAULTS.
    return {k: (list(v) if isinstance(v, list) else v) for k, v in DEFAULTS.items()}


def _coerce(raw, typ, key):
    if typ is bool:
        return raw.strip().lower() in ("1", "true", "yes", "on")
    if typ is int:
        try:
            return int(raw)
        except ValueError as exc:
            raise ConfigError(
                "CLAUDE_PLUGIN_OPTION_{}: expected int, got {!r}".format(key, raw)
            ) from exc
    if typ is list:
        return [s for s in raw.split(",") if s]
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
        _overlay(merged, _strip_meta(_read_json(root / preset_id)))
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
    return errors


def read_config(path=None):
    """Read an already-resolved eval-config.json, or fresh DEFAULTS when path is None.

    Used by scripts so they run standalone (no --config) with default behavior.
    """
    if path:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    return _fresh_defaults()
