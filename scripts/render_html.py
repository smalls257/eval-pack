#!/usr/bin/env python3
import argparse
import html as htmllib
import json
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path


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


def render_transcript_html(transcript_path, pack_dir, screenshots_dir):
    """Render transcript HTML and collect browser screenshots in a single pass."""
    rows = []
    copied = 0
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
                if isinstance(content, list):
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
    (pack_dir / "transcript.html").write_text(page, encoding="utf-8")


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
        shutil.copy(transcript_file, pack_dir / "transcript.jsonl")
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


def load_prior_rounds(zip_path, session_id):
    """Read prior round data from existing zip. Returns (prev_data, prev_screenshot_names)."""
    prev_data = {}
    if zip_path.is_file():
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                for name in zf.namelist():
                    if name.endswith("data.json"):
                        candidate = json.loads(zf.read(name).decode("utf-8"))
                        if candidate.get("sessionId") == session_id:
                            prev_data = candidate
                        break
        except Exception:
            print(f"Warning: could not read prior zip {zip_path}; starting fresh", file=sys.stderr)

    prev_screenshot_names = {
        Path(s.get("path", "")).name
        for r in (prev_data.get("rounds") or [])
        for s in (r.get("screenshots") or [])
    }
    return prev_data, prev_screenshot_names


def collect_new_screenshots(screenshots_dir, prev_screenshot_names):
    """Build screenshot list for this round, excluding prior-round screenshots."""
    screenshots = []
    if screenshots_dir.is_dir():
        for png in sorted(screenshots_dir.glob("*.png")):
            if png.name in prev_screenshot_names:
                continue
            label = png.stem.replace("-", " ").replace("_", " ")
            screenshots.append({"path": f"screenshots/{png.name}", "label": label})
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


def assemble_zip(pack_dir, zip_path, session_id):
    """Write zip from pack_dir contents (excluding .jsonl), then remove pack_dir."""
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for f in pack_dir.rglob("*"):
            if f.is_file() and f.suffix != ".jsonl":
                zf.write(f, f"{session_id}/{f.relative_to(pack_dir)}")
    shutil.rmtree(pack_dir)
    print(f"Eval pack rendered to {zip_path}")


def main():
    parser = argparse.ArgumentParser(description="Render eval pack HTML report")
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("session_id")
    parser.add_argument("plugin_root", type=Path)
    parser.add_argument("transcript_file", type=Path, nargs="?")
    parser.add_argument("--branch", default="", help="Git branch name for zip filename")
    args = parser.parse_args()

    if not re.match(r"^[a-zA-Z0-9._-]+$", args.session_id):
        print(
            f"Error: invalid session_id {args.session_id!r} — must match [a-zA-Z0-9._-]+",
            file=sys.stderr,
        )
        sys.exit(1)

    pack_dir = args.output_dir / args.session_id
    template_dir = args.plugin_root / "templates" / "html"
    scripts_dir = args.plugin_root / "scripts"

    build_directory_structure(pack_dir, template_dir)
    load_round_inputs(pack_dir, args.transcript_file, scripts_dir)

    if args.transcript_file and args.transcript_file.is_file():
        render_transcript_html(args.transcript_file, pack_dir, pack_dir / "screenshots")

    git_branch = args.branch
    zip_name = slugify(git_branch) if git_branch else args.session_id
    zip_path = args.output_dir / f"{zip_name}.zip"
    prev_data, prev_screenshot_names = load_prior_rounds(zip_path, args.session_id)
    screenshots = collect_new_screenshots(pack_dir / "screenshots", prev_screenshot_names)

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
        "rounds": list(prev_data.get("rounds") or []) + [new_round],
        "transcript": load_jsonl(transcript_jsonl) if transcript_jsonl.is_file() else [],
    }

    inject_into_template(pack_dir, data)
    assemble_zip(pack_dir, zip_path, args.session_id)


if __name__ == "__main__":
    main()
