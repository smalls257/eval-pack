#!/usr/bin/env python3
import argparse
import html as htmllib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))  # noqa: E402
import redact  # noqa: E402
from config import read_config  # noqa: E402


def run_script(script_path, args):
    result = subprocess.run(
        [sys.executable, str(script_path)] + [str(a) for a in args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr, end="")
    return result.returncode == 0


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default if default is not None else {}


def slugify(s):
    return re.sub(r"[^a-zA-Z0-9._-]", "-", s.replace("/", "-").replace(" ", "-"))


def load_jsonl(path):
    entries = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                print(f"Warning: skipping malformed JSONL line in {path}", file=sys.stderr)
    return entries


def render_transcript_html(transcript_path, pack_dir, screenshots_dir, rules=()):
    """Render transcript HTML and collect browser screenshots in a single pass."""
    rows = []
    copied = 0
    agent_screenshot_names = set()
    try:
        for entry in load_jsonl(transcript_path):
            role = entry.get("type") or (entry.get("message") or {}).get("role", "")
            msg = entry.get("message") or entry
            content = msg.get("content", "")
            ts = (entry.get("timestamp") or "")[:19]

            # Render human/assistant turns
            if role in ("human", "user"):
                text = (
                    content if isinstance(content, str)
                    else " ".join(
                        b.get("text", "") for b in content
                        if isinstance(b, dict) and b.get("type") == "text"
                    ) if isinstance(content, list)
                    else ""
                )
                if text.strip():
                    rows.append(
                        f'<div class="turn user"><div class="meta">USER {htmllib.escape(ts)}</div>'
                        f"<pre>{htmllib.escape(text)}</pre></div>"
                    )
            elif role == "assistant":
                if isinstance(content, str):
                    text = content.strip()
                    if text:
                        model = (msg.get("model") or "").upper()
                        rows.append(
                            f'<div class="turn assistant"><div class="meta">'
                            f'{htmllib.escape(model or "ASSISTANT")} {htmllib.escape(ts)}</div>'
                            f"<pre>{htmllib.escape(text)}</pre></div>"
                        )
                elif isinstance(content, list):
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        if block.get("type") == "text":
                            text = block.get("text", "").strip()
                            if text:
                                model = (msg.get("model") or "").upper()
                                rows.append(
                                    f'<div class="turn assistant"><div class="meta">'
                                    f'{htmllib.escape(model or "ASSISTANT")} {htmllib.escape(ts)}</div>'
                                    f"<pre>{htmllib.escape(text)}</pre></div>"
                                )
                        elif block.get("type") == "tool_use" and block.get("name") == "Agent":
                            desc = (block.get("input") or {}).get("description", "")
                            model_tag = (block.get("input") or {}).get("model") or (block.get("input") or {}).get("subagent_type", "")
                            if desc:
                                label = f"[{model_tag}] {desc}" if model_tag else desc
                                rows.append(
                                    f'<div class="turn subagent"><div class="meta">→ SUBAGENT {htmllib.escape(ts)}</div>'
                                    f"<pre>{htmllib.escape(label)}</pre></div>"
                                )

            # Collect browser screenshots from ALL tool_use blocks (any role)
            raw_content = msg.get("content") or []
            if isinstance(raw_content, list):
                for block in raw_content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") != "tool_use":
                        continue
                    if not block.get("name", "").endswith("browser_take_screenshot"):
                        continue
                    filename = (block.get("input") or {}).get("filename")
                    if not filename:
                        continue
                    agent_screenshot_names.add(Path(filename).name)
                    src = Path(filename)
                    if not src.is_absolute():
                        src = Path.cwd() / src
                    if src.is_file():
                        dest = screenshots_dir / src.name
                        if not dest.exists():
                            shutil.copy(src, dest)
                            copied += 1

    except Exception as ex:
        rows.append(f'<div class="turn user"><pre>Error rendering transcript: {htmllib.escape(str(ex))}</pre></div>')

    if copied:
        print(f"Collected {copied} screenshot(s) from transcript tool calls")

    page = (
        '<!DOCTYPE html><html><head><meta charset="utf-8"><title>Transcript</title>\n'
        "<style>\n"
        "body{background:#0d0d1a;color:#ccc;font-family:monospace;font-size:13px;padding:16px;margin:0}\n"
        "pre{white-space:pre-wrap;word-break:break-word;margin:4px 0}\n"
        ".turn{margin:8px 0;border-left:3px solid #444;padding:8px 12px}\n"
        ".user{background:#0f3460;border-color:#3a6ea5}\n"
        ".assistant{background:#1a1a2e;border-color:#444}\n"
        ".subagent{background:#1a2e1a;border-color:#3a7a3a}\n"
        ".meta{font-size:11px;color:#888;margin-bottom:4px}\n"
        "</style></head><body>"
        + "".join(rows)
        + "</body></html>"
    )
    page = redact.redact(page, rules)
    (pack_dir / "transcript.html").write_text(page, encoding="utf-8")
    return agent_screenshot_names


def redact_transcript_file(pack_dir, rules):
    """Mask the raw transcript.jsonl in place so secrets never ship in the zip or openable copy."""
    path = pack_dir / "transcript.jsonl"
    if not rules or not path.is_file():
        return
    path.write_text(redact.redact(path.read_text(encoding="utf-8"), rules), encoding="utf-8")


def build_directory_structure(pack_dir, template_dir):
    """Create pack directory layout and copy static templates."""
    pack_dir.mkdir(parents=True, exist_ok=True)
    (pack_dir / "screenshots").mkdir(exist_ok=True)
    (pack_dir / "logs").mkdir(exist_ok=True)
    shutil.copy(template_dir / "index.html", pack_dir / "index.html")
    shutil.copy(template_dir / "styles.css", pack_dir / "styles.css")
    shutil.copy(template_dir / "scripts.js", pack_dir / "scripts.js")


def load_round_inputs(pack_dir, transcript_file, scripts_dir):
    """Run extraction scripts, validate analysis.json, backfill defaults."""
    if transcript_file and transcript_file.is_file():
        dest = pack_dir / "transcript.jsonl"
        # The skill may already pass pack_dir/transcript.jsonl (the canonical
        # merged transcript). Copying a file onto itself raises SameFileError.
        if transcript_file.resolve() != dest.resolve():
            shutil.copy(transcript_file, dest)
        ok = run_script(scripts_dir / "extract_tools.py", [transcript_file, pack_dir])
        if not ok:
            print("Warning: extract_tools.py failed; tool data will be empty", file=sys.stderr)

    analysis_path = pack_dir / "analysis.json"
    if not analysis_path.is_file():
        print(
            f"Error: analysis.json not found in {pack_dir}. Run Step 4 (Analyze) before rendering.",
            file=sys.stderr,
        )
        sys.exit(1)
    analysis_data = read_json(analysis_path)
    if not analysis_data.get("title"):
        print(
            "Error: analysis.json is empty or missing required fields. Run Step 4 (Analyze) before rendering.",
            file=sys.stderr,
        )
        sys.exit(1)

    for name, default in [
        ("metrics.json", "{}"),
        ("patterns.json", "{}"),
        ("test-results.json", "{}"),
        ("tools.json", "{}"),
    ]:
        p = pack_dir / name
        if not p.exists():
            p.write_text(default, encoding="utf-8")


def load_prior_rounds(zip_path):
    """Read prior round data from an existing branch zip.

    Anchor: the zip is named by branch, so its rounds belong to this unit of
    work regardless of which session id produced them — carry them forward
    rather than restarting rounds at every resumed session.
    Returns (prev_data, prev_screenshot_names).
    """
    prev_data = {}
    if zip_path.is_file():
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                for name in zf.namelist():
                    if name.endswith("data.json"):
                        prev_data = json.loads(zf.read(name).decode("utf-8"))
                        break
        except Exception:
            print(f"Warning: could not read prior zip {zip_path}; starting fresh", file=sys.stderr)

    prev_screenshot_names = {
        Path(s.get("path", "")).name
        for r in (prev_data.get("rounds") or [])
        for s in (r.get("screenshots") or [])
    }
    return prev_data, prev_screenshot_names


def _load_screenshot_sources(screenshots_dir):
    """Read screenshots/sources.json — a flat {filename: 'agent'|'test'} map.

    Sensor: provenance must be explicit. A missing or malformed file degrades to an
    empty map (logged, not silently swallowed); callers fall back to the agent set.
    """
    path = screenshots_dir / "sources.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Warning: could not read {path}: {exc}", file=sys.stderr)
        return {}
    if not isinstance(data, dict):
        print(f"Warning: {path} is not a JSON object; ignoring", file=sys.stderr)
        return {}
    valid = {}
    for name, source in data.items():
        if source in ("agent", "test"):
            valid[name] = source
        else:
            print(
                f"Warning: {path} entry {name!r} has unrecognized source {source!r} "
                "(expected 'agent' or 'test'); ignoring",
                file=sys.stderr,
            )
    return valid


def collect_new_screenshots(screenshots_dir, prev_screenshot_names, agent_names):
    """Build screenshot list for this round, excluding prior-round screenshots.

    Each screenshot is tagged with a source: 'agent' if it matches a
    browser_take_screenshot call (or sources.json says so), 'test' if sources.json
    marks it, else 'unknown' — never guess a provenance we cannot prove.
    """
    screenshots = []
    sources = _load_screenshot_sources(screenshots_dir)
    if screenshots_dir.is_dir():
        for png in sorted(screenshots_dir.glob("*.png")):
            if png.name in prev_screenshot_names:
                continue
            label = png.stem.replace("-", " ").replace("_", " ")
            mapped = sources.get(png.name)
            if png.name in agent_names or mapped == "agent":
                source = "agent"
            elif mapped == "test":
                source = "test"
            else:
                source = "unknown"
            screenshots.append(
                {"path": f"screenshots/{png.name}", "label": label, "source": source}
            )
    return screenshots


def inject_into_template(pack_dir, data):
    """Embed eval pack data as window.__EVAL_PACK_DATA__ in index.html."""
    index_path = pack_dir / "index.html"
    html_content = index_path.read_text(encoding="utf-8")
    data_no_transcript = dict(data, transcript=[])
    safe_data = json.dumps(data_no_transcript).replace("</", "<\\/")
    tag = f"<script>window.__EVAL_PACK_DATA__ = {safe_data};</script>"
    if "__EVAL_PACK_DATA__" in html_content:
        html_content = re.sub(
            r"<script>window\.__EVAL_PACK_DATA__.*?</script>",
            tag,
            html_content,
            flags=re.DOTALL,
        )
    else:
        html_content = html_content.replace(
            '<script src="scripts.js">',
            tag + '\n  <script src="scripts.js">',
        )
    index_path.write_text(html_content, encoding="utf-8")
    (pack_dir / "data.json").write_text(
        json.dumps(data_no_transcript, indent=2), encoding="utf-8"
    )


def write_zip(pack_dir, zip_path, session_id, include_transcript=True):
    """Write zip from pack_dir contents. The raw transcript.jsonl is bundled
    only when include_transcript (the `includeTranscript` userConfig)."""
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for f in pack_dir.rglob("*"):
            if f.is_file() and (include_transcript or f.suffix != ".jsonl"):
                zf.write(f, f"{session_id}/{f.relative_to(pack_dir)}")


def publish_openable(pack_dir, session_id, open_base, include_transcript=True):
    """Copy rendered pack to an openable dir outside the repo; return that dir.

    Sensor: the dashboard must be readable without a decompress step. The copy
    lives outside the repo (system temp by default) so it is never pushed.
    The raw .jsonl is included only when include_transcript.
    """
    open_base.mkdir(parents=True, exist_ok=True)
    open_dir = open_base / f"eval-pack-{session_id}"
    if open_dir.exists():
        shutil.rmtree(open_dir)
    ignore = None if include_transcript else shutil.ignore_patterns("*.jsonl")
    shutil.copytree(pack_dir, open_dir, ignore=ignore)
    return open_dir


def _include_transcript():
    """Read the includeTranscript userConfig (env). Default true."""
    val = os.environ.get("CLAUDE_PLUGIN_OPTION_includeTranscript", "true")
    return str(val).strip().lower() not in ("false", "0", "no")


def validate_pack(pack_dir):
    """Return a list of gaps that must block producing the eval pack.

    Sensor, not Silent Fallback: a missing required input must halt loudly and
    produce NO output, rather than emitting a pack with empty placeholders.
    Required: a real transcript (>=1 conversation turn) and metrics (extraction
    actually ran). analysis.json is gated separately in load_round_inputs.
    """
    gaps = []

    transcript = pack_dir / "transcript.jsonl"
    if not transcript.is_file() or transcript.stat().st_size == 0:
        gaps.append("transcript.jsonl is missing or empty")
    else:
        turns = sum(
            1 for e in load_jsonl(transcript)
            if e.get("type") in ("user", "human", "assistant")
            and (e.get("message") or e.get("content"))
        )
        if turns == 0:
            gaps.append("transcript.jsonl has no conversation turns")

    metrics = read_json(pack_dir / "metrics.json")
    if not metrics or not metrics.get("turnCount"):
        gaps.append("metrics.json missing or has no turnCount (metric extraction did not run)")

    return gaps


def main():
    parser = argparse.ArgumentParser(description="Render eval pack HTML report")
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("session_id")
    parser.add_argument("plugin_root", type=Path)
    parser.add_argument("transcript_file", type=Path, nargs="?")
    parser.add_argument("--branch", default="", help="Git branch name for zip filename")
    parser.add_argument(
        "--open-base",
        default="",
        help="Base dir for the openable copy (default: system temp)",
    )
    args = parser.parse_args()

    if not re.match(r"^[a-zA-Z0-9._-]+$", args.session_id):
        print(
            f"Error: invalid session_id {args.session_id!r} — must match [a-zA-Z0-9._-]+",
            file=sys.stderr,
        )
        sys.exit(1)

    pack_dir = args.output_dir / args.session_id
    cfg_path = pack_dir / "eval-config.json"
    cfg = read_config(cfg_path if cfg_path.is_file() else None)
    redaction_rules = cfg["redaction"]
    template_dir = args.plugin_root / "templates" / "html"
    scripts_dir = args.plugin_root / "scripts"

    build_directory_structure(pack_dir, template_dir)
    load_round_inputs(pack_dir, args.transcript_file, scripts_dir)

    gaps = validate_pack(pack_dir)
    if gaps:
        print("Refusing to produce eval pack — incomplete inputs:", file=sys.stderr)
        for g in gaps:
            print(f"  - {g}", file=sys.stderr)
        print("Fix the gap(s) above and re-run; no partial pack was written.", file=sys.stderr)
        shutil.rmtree(pack_dir, ignore_errors=True)
        sys.exit(1)

    agent_screenshot_names = set()
    if args.transcript_file and args.transcript_file.is_file():
        agent_screenshot_names = render_transcript_html(
            args.transcript_file, pack_dir, pack_dir / "screenshots", redaction_rules
        )

    git_branch = args.branch
    zip_name = slugify(git_branch) if git_branch else args.session_id
    zip_path = args.output_dir / f"{zip_name}.zip"
    prev_data, prev_screenshot_names = load_prior_rounds(zip_path)
    screenshots = collect_new_screenshots(
        pack_dir / "screenshots", prev_screenshot_names, agent_screenshot_names
    )

    new_round = {
        "screenshots": screenshots,
        "gitBranch": git_branch,
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    transcript_jsonl = pack_dir / "transcript.jsonl"
    data = {
        "sessionId": args.session_id,
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "analysis": read_json(pack_dir / "analysis.json"),
        "metrics": read_json(pack_dir / "metrics.json"),
        "patterns": read_json(pack_dir / "patterns.json"),
        "testResults": read_json(pack_dir / "test-results.json"),
        "tools": read_json(pack_dir / "tools.json"),
        "lenses": read_json(pack_dir / "lenses.json"),
        "rounds": list(prev_data.get("rounds") or []) + [new_round],
        "transcript": load_jsonl(transcript_jsonl) if transcript_jsonl.is_file() else [],
    }

    inject_into_template(pack_dir, data)

    redact_transcript_file(pack_dir, redaction_rules)

    include_transcript = _include_transcript()
    write_zip(pack_dir, zip_path, args.session_id, include_transcript)
    print(f"Eval pack rendered to {zip_path}")

    if cfg["publishOpenable"]:
        open_base = (
            Path(cfg["openableDir"]) if cfg["openableDir"]
            else (Path(args.open_base) if args.open_base else Path(tempfile.gettempdir()))
        )
        try:
            open_dir = publish_openable(pack_dir, args.session_id, open_base, include_transcript)
            print(f"Open: file://{open_dir}/index.html")
        except Exception as ex:
            # Buffer: the zip is the durable artifact; the openable copy is a convenience.
            print(f"Warning: could not write openable copy: {ex}", file=sys.stderr)

    shutil.rmtree(pack_dir)


if __name__ == "__main__":
    main()
