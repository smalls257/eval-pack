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
    # Commands the generate skill runs verbatim to determine the test verdict; empty = detect.
    "testCommands": [],
    # Ticket-key regex the review skill matches for PR-body linking.
    "ticketPattern": r"[A-Z][A-Z0-9]+-[0-9]+",
    # Regex patterns whose matches are masked in published transcripts (security).
    # Note: a LEADING "!replace" is the list-replace sentinel, not a pattern, and the
    # literal string is never legal in a resolved list (leak guard in validate()); to
    # mask that text use an equivalent regex, e.g. "!replac[e]".
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
    "analysisLenses": [
        {"skill": "review", "role": "contributor"},
        {"skill": "business-risk", "role": "contributor", "display": "both"},
        {"skill": "friction", "role": "contributor"},
        {"skill": "repo-improvements", "role": "contributor"},
        {"skill": "user-improvements", "role": "contributor"},
        {"skill": "sycophancy", "role": "contributor", "display": "both"},
        {"skill": "requirement-drift", "role": "scorer"},
        {"skill": "verification-rigor", "role": "scorer"},
    ],
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
    "repoBaseUrl": "",
    "messages": {},
    # Project-relative dir holding report template overrides (index.html/styles.css/scripts.js);
    # empty means the bundled templates.
    "templateDir": "",
    # Heuristic detection regexes (lists are OR-combined). Defaults are today's English patterns.
    "detectionPatterns": {
        "done": [r"(?i)(done|complete|finished|all set|that should|looks good now)"],
        "correction": [r"(?i)(no|not|wrong|still|actually|but|fix|fail|error|broken|issue)"],
        "retry": [r"(?i)(try again|retry|let me try|another approach|different approach)"],
    },
    # How many following entries to scan for a user correction after a completion claim.
    "falseCompletionWindow": 1,
    # Truncation length for quoted claim/response text in patterns.json.
    "claimTruncLen": 120,
    # Per-flag severity overrides: {flagId: "red"|"amber"|"green"|"off"}. Empty = built-in levels.
    "flagSeverities": {},
    # Pipeline options, unified from the legacy pluginConfigs home. The
    # CLAUDE_PLUGIN_OPTION_* env layer keeps old plugin-option settings working.
    "outputDir": ".eval-packs",
    "analysis": True,
    "includeRawTranscript": False,
    "includeRenderedTranscript": True,
    "ticketBaseUrl": "",
    # Declarative policy checks: {id, level, label, scope, pattern, threshold?} — deterministic
    # regex checks over the recorded session, feeding the flags/verdict pipeline. No code exec.
    "customDetectors": [],
    # Repo-relative scripts run by detect_patterns; each prints {"flags":[...]} (validated).
    # Same trust class as testCommands: your repo's own code.
    "detectorScripts": [],
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
    "repoBaseUrl": str,
    "messages": dict,
    "templateDir": str,
    "detectionPatterns": dict,
    "falseCompletionWindow": int,
    "claimTruncLen": int,
    "flagSeverities": dict,
    "outputDir": str,
    "analysis": bool,
    "includeRawTranscript": bool,
    "includeRenderedTranscript": bool,
    "ticketBaseUrl": str,
    "customDetectors": list,
    "detectorScripts": list,
}

# Keys consumed during merge or by editors only — never part of the resolved config.
_META_KEYS = {"extends", "$schema"}

# List keys whose elements are regexes — comma shorthand would corrupt them (e.g. "a{1,3}"),
# so env overrides for these MUST be JSON arrays.
_COMMA_UNSAFE_KEYS = {"redaction"}

# Allowed verdict aggregation rules (shared with scripts/aggregate.py).
AGGREGATION_RULES = ("core", "min", "mean")

# Allowed report themes.
THEMES = ("dark", "light", "system")
DISPLAY_MODES = ("card", "tab", "both")

# Model tiers a lens's subagent may be pinned to (cost/quality tuning). Mirrors the Agent
# tool's model aliases; a lens with no model inherits the session model.
LENS_MODELS = ("opus", "sonnet", "haiku", "fable")

# Allowed per-flag severity overrides.
FLAG_LEVELS = ("red", "amber", "green", "off")

# Scopes a declarative custom detector can scan.
DETECTOR_SCOPES = ("bash", "files", "text", "user")

# Flag ids that can signal failure (used by the can-never-fail guard). Green-only ids
# (testsPassing, cleanPass) are excluded — keep in sync with detect_patterns.main.
FAILURE_FLAG_IDS = (
    "testsFailing", "unknownVerdict", "falseCompletions",
    "highRetry", "scopeDrift", "partialSession",
)

# Every flag id the built-in pipeline can emit (collision guard for customDetectors).
BUILTIN_FLAG_IDS = FAILURE_FLAG_IDS + (
    "testsPassing", "cleanPass", "flagsSuppressed", "lensFailed", "lensVerdict",
    "detectorFailed",
)


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
            if v and v[0] == "!replace":
                # explicit replace: user opts out of additive merge for this list
                base[k] = list(v[1:])
            else:
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
    """Coerce a raw env string to typ.

    Encoding contract: values starting with '[' or '{' are parsed as JSON (the only
    way to express dicts, nested values, or comma-containing elements like regexes);
    other list values use the comma shorthand for simple token lists. Regex-bearing
    list keys (_COMMA_UNSAFE_KEYS) reject the shorthand outright.
    """
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
    if typ in (list, dict):
        raw_s = raw.strip()
        if raw_s.startswith("[") or raw_s.startswith("{"):
            try:
                val = json.loads(raw_s)
            except json.JSONDecodeError as exc:
                raise ConfigError(
                    "CLAUDE_PLUGIN_OPTION_{}: invalid JSON ({})".format(key, exc)) from exc
            if not isinstance(val, typ):
                raise ConfigError("CLAUDE_PLUGIN_OPTION_{}: expected {}, got {}".format(
                    key, typ.__name__, type(val).__name__))
            # Dedupe to match the file-layer list-merge semantics (consistency).
            if typ is list:
                if val and val[0] == "!replace":
                    # env values replace anyway — consume the sentinel so it can never
                    # leak into a resolved list as literal data
                    val = val[1:]
                return _dedupe(val)
            return val
        if typ is dict:
            raise ConfigError(
                "CLAUDE_PLUGIN_OPTION_{}: dict values must be JSON (e.g. '{{\"k\": \"v\"}}')".format(key))
        if key in _COMMA_UNSAFE_KEYS:
            raise ConfigError(
                "CLAUDE_PLUGIN_OPTION_{}: values may contain commas (regexes) — "
                "use a JSON array, e.g. '[\"secret{{1,3}}\"]'".format(key))
        # legacy comma-list shorthand for simple token lists
        return _dedupe([s for s in raw.split(",") if s])
    return raw


def coerce_env_bool(raw, key):
    """Public canonical env->bool coercion (same contract as the env layer).

    Accepts the env layer's spellings (1/true/yes/on, 0/false/no/off) and
    raises ConfigError on anything else — callers outside the layered loader
    (e.g. standalone renders) must not hand-roll a divergent parser.
    """
    return _coerce(raw, bool, key)


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
    CLAUDE_PLUGIN_OPTION_* env override REPLACES the list outright. A
    file-layer list starting with "!replace" replaces the base list instead
    of concatenating. The leak invariant (no literal sentinel in a resolved
    list) is enforced by validate(), not by this loader — callers must
    validate before trusting list values. Raises ConfigError on malformed
    JSON or an uncoercible env value.
    """
    env = os.environ if env is None else env
    root = Path(project_root)
    project_cfg = _read_json(root / ".eval-pack.json")
    local_cfg = _read_json(root / ".eval-pack.local.json")
    if "extends" in local_cfg:
        raise ConfigError(
            "extends is not allowed in .eval-pack.local.json (project file only) — "
            "it would be silently ignored otherwise")

    merged = _fresh_defaults()
    root_resolved = root.resolve()
    # extends is single-level and project-only: presets cannot themselves extend.
    for preset_id in project_cfg.get("extends", []):
        preset_path = root / preset_id
        # Confine presets to the repo: reject ../ escapes and absolute paths outside root.
        resolved = preset_path.resolve()
        if not (resolved == root_resolved or root_resolved in resolved.parents):
            raise ConfigError("extends: preset {!r} resolves outside the repo".format(preset_id))
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
    rubric = cfg.get("rubric")
    if isinstance(rubric, dict):
        for band, criteria in rubric.items():
            if not isinstance(criteria, str):
                errors.append("rubric.{}: criteria must be a string, got {}".format(
                    band, type(criteria).__name__))
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
            if isinstance(lens, dict) and "template" in lens and not isinstance(lens.get("template"), str):
                errors.append("analysisLenses[{}]: template must be a string path".format(i))
            if isinstance(lens, dict) and "version" in lens and not isinstance(lens.get("version"), str):
                errors.append("analysisLenses[{}]: version must be a string".format(i))
            if isinstance(lens, dict) and "display" in lens and lens.get("display") not in DISPLAY_MODES:
                errors.append("analysisLenses[{}]: display must be one of: {}".format(
                    i, ", ".join(repr(m) for m in DISPLAY_MODES)))
            if isinstance(lens, dict) and "model" in lens and lens.get("model") not in LENS_MODELS:
                errors.append("analysisLenses[{}]: model must be one of: {}".format(
                    i, ", ".join(repr(m) for m in LENS_MODELS)))
    theme = cfg.get("defaultTheme")
    if theme is not None and theme not in THEMES:
        errors.append("defaultTheme: {!r} is not one of {}".format(theme, list(THEMES)))
    # Non-negative bound: a negative truncation length is a garbage (negative-index) slice.
    n = cfg.get("skillArgsMaxLen")
    if isinstance(n, int) and not isinstance(n, bool) and n < 0:
        errors.append("skillArgsMaxLen: must be >= 0, got {}".format(n))
    dp = cfg.get("detectionPatterns")
    if isinstance(dp, dict):
        for group, pats in dp.items():
            if not isinstance(pats, list):
                errors.append("detectionPatterns.{}: expected list of regexes".format(group))
                continue
            for pat in pats:
                try:
                    re.compile(pat)
                except re.error as exc:
                    errors.append("detectionPatterns.{}: invalid regex {!r} ({})".format(group, pat, exc))
    sevs = cfg.get("flagSeverities")
    if isinstance(sevs, dict):
        for fid, level in sevs.items():
            if level not in FLAG_LEVELS:
                errors.append("flagSeverities.{}: {!r} is not one of {}".format(fid, level, list(FLAG_LEVELS)))
    # The merge sentinel is consumed by _overlay/_coerce; a literal survivor means a
    # misplaced sentinel (not first element) or an unforeseen path — never legal data.
    for k, typ in _TYPES.items():
        if typ is list and isinstance(cfg.get(k), list) and "!replace" in cfg[k]:
            errors.append(
                "{}: literal '!replace' in resolved list — in a file layer the sentinel must "
                "be the FIRST element (or omitted); for an env override use the JSON-array "
                "form, which consumes it (env values replace anyway)".format(k))
        elif typ is dict and isinstance(cfg.get(k), dict):
            # Dicts replace wholesale — the list sentinel is meaningless inside them and
            # would compile into detection regexes as literal text. Fail loud.
            for group, val in cfg[k].items():
                if isinstance(val, list) and "!replace" in val:
                    errors.append(
                        "{}.{}: '!replace' is a LIST-merge sentinel; dict values replace "
                        "wholesale — remove it and supply every group you want".format(k, group))
    dets = cfg.get("customDetectors")
    if isinstance(dets, list):
        seen_ids = set()
        for i, det in enumerate(dets):
            if not isinstance(det, dict) or not det.get("id") or not det.get("label"):
                errors.append("customDetectors[{}]: needs id, level, label, scope, pattern".format(i))
                continue
            det_id = det["id"]
            if det_id in BUILTIN_FLAG_IDS:
                errors.append("customDetectors[{}]: id {!r} collides with a built-in flag id".format(i, det_id))
            if det_id in seen_ids:
                errors.append("customDetectors[{}]: duplicate id {!r}".format(i, det_id))
            seen_ids.add(det_id)
            if det.get("level") not in ("red", "amber", "green"):
                errors.append("customDetectors[{}]: level must be red|amber|green".format(i))
            if det.get("scope") not in DETECTOR_SCOPES:
                errors.append("customDetectors[{}]: scope must be one of {}".format(
                    i, list(DETECTOR_SCOPES)))
            try:
                re.compile(det.get("pattern") or "")
            except re.error as exc:
                errors.append("customDetectors[{}]: invalid pattern ({})".format(i, exc))
            th = det.get("threshold", 1)
            if isinstance(th, bool) or not isinstance(th, int) or th < 1:
                errors.append("customDetectors[{}]: threshold must be an int >= 1".format(i))
    return errors


def read_config(path=None):
    """Read an already-resolved eval-config.json, or fresh DEFAULTS when path is None.

    Used by scripts so they run standalone (no --config) with default behavior.
    """
    if path:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    return _fresh_defaults()
