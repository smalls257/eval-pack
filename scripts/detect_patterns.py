#!/usr/bin/env python3
import argparse
import json
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))  # noqa: E402
from config import read_config  # noqa: E402


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


DONE_RE = re.compile(r"(?i)(done|complete|finished|all set|that should|looks good now)")
CORRECTION_RE = re.compile(r"(?i)(no|not|wrong|still|actually|but|fix|fail|error|broken|issue)")
RETRY_RE = re.compile(r"(?i)(try again|retry|let me try|another approach|different approach)")


def detect_false_completions(entries):
    result = []
    for i in range(len(entries) - 1):
        if entries[i].get("type") == "assistant" and is_human(entries[i + 1]):
            agent_text = entry_text(entries[i])
            user_text = entry_text(entries[i + 1])
            if DONE_RE.search(agent_text) and CORRECTION_RE.search(user_text):
                result.append({
                    "turn": i,
                    "agentClaim": agent_text[:120],
                    "userResponse": user_text[:120],
                })
    return result


def detect_retries(entries):
    return sum(
        1 for e in entries
        if e.get("type") == "assistant" and RETRY_RE.search(entry_text(e))
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


def main():
    parser = argparse.ArgumentParser(description="Detect heuristic patterns in transcript")
    parser.add_argument("transcript", help="Path to transcript.jsonl")
    parser.add_argument("output_dir", help="Directory to write pattern output")
    parser.add_argument("--config", default=None, help="Path to resolved eval-config.json")
    args = parser.parse_args()
    cfg = read_config(args.config)

    transcript_file = Path(args.transcript)
    output_dir = Path(args.output_dir)

    if not transcript_file.is_file():
        print(f"Error: transcript file not found: {transcript_file}", file=sys.stderr)
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)
    entries = load_jsonl(transcript_file)

    false_completions = detect_false_completions(entries)
    retry_count = detect_retries(entries)
    scope_drift = check_scope_drift(output_dir, cfg["scopeDriftFileThreshold"])
    partial_session = detect_partial_session(entries)

    test_verdict = read_test_verdict(output_dir)

    flags = []
    if test_verdict == "fail":
        flags.append({"level": "red", "label": "Tests failing at completion"})
    elif test_verdict == "pass":
        flags.append({"level": "green", "label": "Tests passing at completion"})
    if false_completions:
        flags.append({"level": "amber", "label": "False completions", "count": len(false_completions)})
    if retry_count >= cfg["retryAmberThreshold"]:
        flags.append({"level": "amber", "label": "High retry count", "count": retry_count})
    if scope_drift:
        flags.append({"level": "amber", "label": "Scope drift — many files changed"})
    if partial_session:
        flags.append({
            "level": "amber",
            "label": "Partial session — earlier turns may be missing",
        })
    if not flags:
        flags.append({"level": "green", "label": "Clean first-pass implementation"})

    result = {
        "falseCompletions": false_completions,
        "retryCount": retry_count,
        "scopeDrift": scope_drift,
        "partialSession": partial_session or False,
        "flags": flags,
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
