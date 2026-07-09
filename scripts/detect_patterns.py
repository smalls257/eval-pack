#!/usr/bin/env python3
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))  # noqa: E402
from config import read_config, BUILTIN_FLAG_IDS  # noqa: E402


def load_jsonl(path):
    entries = []
    skipped = 0
    try:
        f_handle = open(path, encoding="utf-8")
    except OSError as exc:
        print(f"Error: could not open {path}: {exc}", file=sys.stderr)
        sys.exit(1)
    with f_handle as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                skipped += 1
                print(f"Warning: skipping malformed JSON on line {line_no}", file=sys.stderr)
    if skipped:
        print(f"Warning: {skipped} line(s) skipped due to JSON parse errors", file=sys.stderr)
    return entries


def entry_text(entry):
    content = (entry.get("message") or {}).get("content") or entry.get("content") or ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            b.get("text", "")
            for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        )
    return str(content)


def is_human(entry):
    return entry.get("type") in ("user", "human")


# Defaults mirror config.DEFAULTS["detectionPatterns"]; kept here so the module works standalone.
DEFAULT_PATTERNS = {
    "done": [r"(?i)(done|complete|finished|all set|that should|looks good now)"],
    "correction": [r"(?i)(no|not|wrong|still|actually|but|fix|fail|error|broken|issue)"],
    "retry": [r"(?i)(try again|retry|let me try|another approach|different approach)"],
}

# Tools whose input.file_path the "files" detector scope observes.
FILE_TOOLS = ("Read", "Edit", "Write", "NotebookEdit", "MultiEdit")


# A leading global flag group like (?i)… must be rewritten to a scoped (?i:…)
# before OR-joining: Python 3.11+ rejects global flags anywhere but position 0.
_GLOBAL_FLAGS_RE = re.compile(r"^\(\?([aiLmsux]+)\)")


def _scoped(pat):
    m = _GLOBAL_FLAGS_RE.match(pat)
    if m:
        return "(?{}:{})".format(m.group(1), pat[m.end():])
    return "(?:{})".format(pat)


def compile_patterns(patterns):
    """OR-combine each group's regex list into one compiled pattern per group."""
    return {
        group: re.compile("|".join(_scoped(p) for p in pats))
        for group, pats in patterns.items()
    }


def detect_false_completions(entries, rx, window, trunc):
    result = []
    for i in range(len(entries) - 1):
        if entries[i].get("type") != "assistant":
            continue
        agent_text = entry_text(entries[i])
        if not rx["done"].search(agent_text):
            continue
        for j in range(i + 1, min(i + 1 + window, len(entries))):
            if not is_human(entries[j]):
                continue
            user_text = entry_text(entries[j])
            if rx["correction"].search(user_text):
                result.append({
                    "turn": i,
                    "agentClaim": agent_text[:trunc],
                    "userResponse": user_text[:trunc],
                })
            break  # judge only the first human reply in the window
    return result


def detect_retries(entries, retry_re):
    return sum(
        1 for e in entries
        if e.get("type") == "assistant" and retry_re.search(entry_text(e))
    )


def detect_partial_session(entries):
    """Detect a transcript that begins mid-conversation.

    Sensor: a session resumed or handed off into a fresh file starts mid-thread,
    so earlier turns live in a prior file and are absent here. An eval computed on
    a partial transcript must declare its coverage, not silently report a fragment
    as the whole session. Returns a detail dict when partial, else None.
    """
    uuids = {e.get("uuid") for e in entries if e.get("uuid")}
    first_msg = None
    for e in entries:
        if e.get("type") in ("user", "assistant") and e.get("message"):
            first_msg = e
            break
    if first_msg is None:
        return None
    parent = first_msg.get("parentUuid")
    starts_mid_thread = bool(parent) and parent not in uuids
    starts_with_compact_summary = bool(first_msg.get("isCompactSummary"))
    if not (starts_mid_thread or starts_with_compact_summary):
        return None
    return {
        "startsMidThread": starts_mid_thread,
        "startsWithCompactSummary": starts_with_compact_summary,
    }


def read_test_verdict(output_dir):
    """Return the final test verdict from test-results.json.

    Returns the recorded verdict string ('pass' | 'fail' | 'none'), or None when the
    file is missing or unreadable (logged, not silently swallowed). The test flag is
    derived from this real end-state — not from counting failure words in the transcript
    (a Paper Tiger signal that fires on normal TDD red→green chatter).
    """
    results_path = Path(output_dir) / "test-results.json"
    if not results_path.is_file():
        print(
            f"Warning: test-results.json not found at {results_path}; no test flag",
            file=sys.stderr,
        )
        return None
    try:
        data = json.loads(results_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Warning: could not read test-results.json: {exc}", file=sys.stderr)
        return None
    return data.get("verdict")


def read_json_safe(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def check_scope_drift(output_dir, threshold):
    metrics_path = Path(output_dir) / "metrics.json"
    if not metrics_path.is_file():
        print(
            f"Warning: metrics.json not found at {metrics_path}; scope drift unknown",
            file=sys.stderr,
        )
        return False
    try:
        data = json.loads(metrics_path.read_text(encoding="utf-8"))
        return (data.get("filesChanged") or 0) > threshold
    except json.JSONDecodeError as exc:
        print(f"Warning: could not parse metrics.json — scope drift unknown: {exc}", file=sys.stderr)
        return False
    except OSError as exc:
        print(f"Warning: could not read metrics.json — scope drift unknown: {exc}", file=sys.stderr)
        return False


def collect_scope_strings(entries):
    """Extract the scannable strings per detector scope from the transcript."""
    scopes = {"bash": [], "files": [], "text": [], "user": []}
    for e in entries:
        etype = e.get("type")
        msg = e.get("message") or e
        content = msg.get("content")
        if isinstance(content, str):
            if etype == "assistant":
                scopes["text"].append(content)
            elif etype in ("user", "human"):
                scopes["user"].append(content)
            continue
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                target = "text" if etype == "assistant" else "user"
                scopes[target].append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                inp = block.get("input") or {}
                if block.get("name") == "Bash":
                    scopes["bash"].append(str(inp.get("command", "")))
                elif block.get("name") in FILE_TOOLS:
                    scopes["files"].append(str(inp.get("file_path", "")))
    return scopes


def run_custom_detectors(detectors, scope_strings):
    """Deterministic policy checks: returns [(id, level, label, count)] for fired detectors."""
    fired = []
    for det in detectors:
        try:
            rx = re.compile(det["pattern"])
        except re.error as exc:
            # Sensor: a policy check that silently doesn't run reads as "clean" — warn loudly.
            # (Resolve-time validation catches this in the pipeline; this guards standalone runs.)
            print(
                "Warning: customDetector {!r} pattern failed to compile ({}); skipped".format(
                    det.get("id"), exc),
                file=sys.stderr,
            )
            continue
        count = sum(1 for s in scope_strings.get(det["scope"], []) if rx.search(s))
        if count >= det.get("threshold", 1):
            fired.append((det["id"], det["level"], det["label"], count))
    return fired


def run_detector_scripts(scripts, transcript_path, output_dir):
    """Run repo detector scripts; validate their output by code. A failing or malformed
    script becomes a visible red flag — never a crash, never a silent absence."""
    ok_flags, failures = [], []
    for script in scripts:
        name = Path(script).name
        try:
            proc = subprocess.run(
                [sys.executable, str(script), str(transcript_path), str(output_dir)],
                capture_output=True, text=True, timeout=120)
            if proc.returncode != 0:
                failures.append((name, "exit {}".format(proc.returncode)))
                continue
            data = json.loads(proc.stdout)
            flags = data.get("flags")
            if not isinstance(flags, list):
                raise ValueError("no flags list")
            for f in flags:
                if (not isinstance(f, dict) or not f.get("id") or not f.get("label")
                        or f.get("level") not in ("red", "amber", "green")):
                    raise ValueError("bad flag shape: {!r}".format(f))
                if f.get("id") in BUILTIN_FLAG_IDS:
                    raise ValueError("script flag id {!r} collides with a built-in".format(f.get("id")))
            ok_flags.extend(flags)
        except (subprocess.TimeoutExpired, json.JSONDecodeError, ValueError, OSError) as exc:
            failures.append((name, str(exc)))
    return ok_flags, failures


def main():
    parser = argparse.ArgumentParser(description="Detect heuristic patterns in transcript")
    parser.add_argument("transcript", help="Path to transcript.jsonl")
    parser.add_argument("output_dir", help="Directory to write pattern output")
    parser.add_argument("--config", default=None, help="Path to resolved eval-config.json")
    args = parser.parse_args()
    cfg = read_config(args.config)
    rx = compile_patterns(cfg.get("detectionPatterns") or DEFAULT_PATTERNS)

    transcript_file = Path(args.transcript)
    output_dir = Path(args.output_dir)

    if not transcript_file.is_file():
        print(f"Error: transcript file not found: {transcript_file}", file=sys.stderr)
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)
    entries = load_jsonl(transcript_file)

    false_completions = detect_false_completions(
        entries, rx, cfg["falseCompletionWindow"], cfg["claimTruncLen"]
    )
    retry_count = detect_retries(entries, rx["retry"])
    scope_drift = check_scope_drift(output_dir, cfg["scopeDriftFileThreshold"])
    partial_session = detect_partial_session(entries)

    test_verdict = read_test_verdict(output_dir)

    # Built-in flags carry a stable id so users can retune severity per-flag.
    sev = cfg.get("flagSeverities") or {}
    suppressed = []
    suppressed_red = []

    def add_flag(fid, default_level, label, **extra):
        level = sev.get(fid, default_level)
        if level == "off":
            suppressed.append(fid)
            if default_level == "red":
                suppressed_red.append(fid)
            return
        flags.append(dict({"id": fid, "level": level, "label": label}, **extra))

    flags = []
    if test_verdict == "fail":
        add_flag("testsFailing", "red", "Tests failing at completion")
    elif test_verdict == "pass":
        add_flag("testsPassing", "green", "Tests passing at completion")
    elif test_verdict not in ("", None, "none"):
        # An unrecognized verdict must be visible, not silently identical to a clean run.
        add_flag("unknownVerdict", "amber", f"Unknown test verdict: {test_verdict!r}")
    if false_completions:
        add_flag("falseCompletions", "amber", "False completions", count=len(false_completions))
    if retry_count >= cfg["retryAmberThreshold"]:
        add_flag("highRetry", "amber", "High retry count", count=retry_count)
    if scope_drift:
        add_flag("scopeDrift", "amber", "Scope drift — many files changed")
    if partial_session:
        add_flag("partialSession", "amber", "Partial session — earlier turns may be missing")
    budget = cfg.get("costBudgetTokens") or 0
    if budget > 0:
        metrics = read_json_safe(output_dir / "metrics.json")
        if not metrics:
            # Sensor: a configured budget must not silently no-op on missing metrics.
            print(
                "Warning: metrics.json missing or unreadable — token budget check skipped",
                file=sys.stderr,
            )
        total = (metrics or {}).get("totalTokens") or 0
        if total > budget:
            # "incl. cache" disambiguates from the report header's cache-exclusive token stat.
            add_flag("overBudget", "amber",
                     f"Over token budget ({total:,} incl. cache > {budget:,})")
    custom = cfg.get("customDetectors") or []
    if custom:
        scope_strings = collect_scope_strings(entries)
        for fid, level, label, count in run_custom_detectors(custom, scope_strings):
            add_flag(fid, level, label, count=count)
    scripts = cfg.get("detectorScripts") or []
    if scripts:
        script_flags, script_failures = run_detector_scripts(scripts, transcript_file, output_dir)
        for f in script_flags:
            add_flag(f["id"], f["level"], f["label"],
                     **({"count": f["count"]} if isinstance(f.get("count"), int) else {}))
        for name, err in script_failures:
            # detectorFailed is intentionally NOT suppressible via flagSeverities: it is the
            # can't-vanish gate for detector scripts — a config that could turn it off would
            # recreate the silent-absence hole it exists to close (mirrors lensFailed).
            flags.append({"id": "detectorFailed", "level": "red",
                          "label": "Detector script failed: {} ({})".format(name, err)})
    if not flags:
        if suppressed:
            # Suppression must not masquerade as a clean pass — say what was hidden.
            # No `count` field: the renderer appends " (count)" and the label already says it.
            flags.append({
                "id": "flagsSuppressed", "level": "amber",
                "label": f"No flags shown — {len(suppressed)} suppressed by flagSeverities",
            })
        else:
            flags.append({"id": "cleanPass", "level": "green", "label": "Clean first-pass implementation"})
    elif suppressed_red:
        # A suppressed RED must not silently downgrade the banner to the surviving flags'
        # level — say which red(s) were turned off (Sensor: no invisible downgrades).
        flags.append({
            "id": "flagsSuppressed", "level": "amber",
            "label": "Red flag(s) suppressed by flagSeverities: {}".format(", ".join(suppressed_red)),
        })

    result = {
        "falseCompletions": false_completions,
        "retryCount": retry_count,
        "scopeDrift": scope_drift,
        "partialSession": partial_session or False,
        "flags": flags,
        "suppressedFlags": suppressed,
    }

    out_path = output_dir / "patterns.json"
    try:
        out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    except OSError as exc:
        print(f"Error: could not write {out_path}: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"Patterns written to {out_path}")


if __name__ == "__main__":
    main()
