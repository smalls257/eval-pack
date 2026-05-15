#!/usr/bin/env python3
import json
import re
import sys
from pathlib import Path


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
FAILURE_RE = re.compile(r"(?i)(FAIL|test failed|tests? failing|assertion.?error|expect.* to |error:.*test)")


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


def detect_test_failures(entries):
    return sum(
        1 for e in entries
        if e.get("type") == "assistant" and FAILURE_RE.search(entry_text(e))
    )


def tests_passed_at_end(output_dir):
    results_path = Path(output_dir) / "test-results.json"
    if not results_path.is_file():
        return False
    try:
        data = json.loads(results_path.read_text(encoding="utf-8"))
        return data.get("verdict") == "pass"
    except (json.JSONDecodeError, OSError):
        return False


def check_scope_drift(output_dir):
    metrics_path = Path(output_dir) / "metrics.json"
    if not metrics_path.is_file():
        return False
    try:
        data = json.loads(metrics_path.read_text(encoding="utf-8"))
        return (data.get("filesChanged") or 0) > 10
    except json.JSONDecodeError as exc:
        print(f"Warning: could not parse metrics.json — scope drift unknown: {exc}", file=sys.stderr)
        return False
    except OSError as exc:
        print(f"Warning: could not read metrics.json — scope drift unknown: {exc}", file=sys.stderr)
        return False


def main():
    if len(sys.argv) < 3:
        print("Usage: detect_patterns.py <transcript.jsonl> <output-dir>", file=sys.stderr)
        sys.exit(1)

    transcript_file = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])

    if not transcript_file.is_file():
        print(f"Error: transcript file not found: {transcript_file}", file=sys.stderr)
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)
    entries = load_jsonl(transcript_file)

    false_completions = detect_false_completions(entries)
    retry_count = detect_retries(entries)
    test_failures = detect_test_failures(entries)
    scope_drift = check_scope_drift(output_dir)

    final_pass = tests_passed_at_end(output_dir)

    flags = []
    if test_failures > 0 and not final_pass:
        flags.append({"level": "red", "label": "Test failures during session", "count": test_failures})
    if false_completions:
        flags.append({"level": "amber", "label": "False completions", "count": len(false_completions)})
    if retry_count > 3:
        flags.append({"level": "amber", "label": "High retry count", "count": retry_count})
    if scope_drift:
        flags.append({"level": "amber", "label": "Scope drift — many files changed"})
    if not flags:
        flags.append({"level": "green", "label": "Clean first-pass implementation"})

    result = {
        "falseCompletions": false_completions,
        "retryCount": retry_count,
        "testFailureCount": test_failures,
        "scopeDrift": scope_drift,
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
