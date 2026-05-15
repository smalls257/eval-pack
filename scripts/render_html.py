#!/usr/bin/env python3
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


def run_git(args, cwd=None):
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            cwd=str(cwd) if cwd else None,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except FileNotFoundError:
        return ""


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


def render_transcript_html(transcript_path, pack_dir):
    rows = []
    try:
        for entry in load_jsonl(transcript_path):
            role = entry.get("type") or (entry.get("message") or {}).get("role", "")
            msg = entry.get("message") or entry
            content = msg.get("content", "")
            ts = (entry.get("timestamp") or "")[:19]

            if role in ("human", "user"):
                text = (
                    content if isinstance(content, str)
                    else " ".join(
                        b.get("text", "") for b in content
                        if isinstance(b, dict) and b.get("type") == "text"
                    ) if isinstance(content, list)
                    else ""
                )
                if not text.strip():
                    continue
                rows.append(
                    f'<div class="turn user"><div class="meta">USER {htmllib.escape(ts)}</div>'
                    f"<pre>{htmllib.escape(text)}</pre></div>"
                )
            elif role == "assistant":
                if not isinstance(content, list):
                    continue
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
    except Exception as ex:
        rows.append(f'<div class="turn user"><pre>Error rendering transcript: {htmllib.escape(str(ex))}</pre></div>')

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


def _collect_screenshots_from_transcript(transcript_file, screenshots_dir):
    copied = 0
    for entry in load_jsonl(transcript_file):
        msg = entry.get("message") or entry
        content = msg.get("content") or []
        if not isinstance(content, list):
            continue
        for block in content:
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
            if not src.is_file():
                continue
            dest = screenshots_dir / src.name
            if not dest.exists():
                shutil.copy(src, dest)
                copied += 1
    if copied:
        print(f"Collected {copied} screenshot(s) from transcript tool calls")



def main():
    if len(sys.argv) < 4:
        print(
            "Usage: render_html.py <output-dir> <session-id> <plugin-root> [transcript-file]",
            file=sys.stderr,
        )
        sys.exit(1)

    output_dir = Path(sys.argv[1])
    session_id = sys.argv[2]
    plugin_root = Path(sys.argv[3])
    transcript_file = Path(sys.argv[4]) if len(sys.argv) > 4 else None

    pack_dir = output_dir / session_id
    template_dir = plugin_root / "templates" / "html"
    scripts_dir = plugin_root / "scripts"

    pack_dir.mkdir(parents=True, exist_ok=True)
    screenshots_dir = pack_dir / "screenshots"
    screenshots_dir.mkdir(exist_ok=True)
    (pack_dir / "logs").mkdir(exist_ok=True)

    shutil.copy(template_dir / "index.html", pack_dir / "index.html")
    shutil.copy(template_dir / "styles.css", pack_dir / "styles.css")
    shutil.copy(template_dir / "scripts.js", pack_dir / "scripts.js")

    if transcript_file and transcript_file.is_file():
        shutil.copy(transcript_file, pack_dir / "transcript.jsonl")
        ok = run_script(scripts_dir / "extract_tools.py", [transcript_file, pack_dir])
        if not ok:
            print("Warning: extract_tools.py failed; tool data will be empty", file=sys.stderr)
        _collect_screenshots_from_transcript(transcript_file, screenshots_dir)

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

    git_branch = (
        run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=output_dir)
        or run_git(["rev-parse", "--abbrev-ref", "HEAD"])
        or ""
    )
    zip_name = slugify(git_branch) if git_branch else session_id

    prev_data = {}
    zip_path = output_dir / f"{zip_name}.zip"
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
            prev_data = {}

    prev_screenshot_names = {
        Path(s.get("path", "")).name
        for r in (prev_data.get("rounds") or [])
        for s in (r.get("screenshots") or [])
    }
    screenshots = []
    if screenshots_dir.is_dir():
        for png in sorted(screenshots_dir.glob("*.png")):
            if png.name in prev_screenshot_names:
                continue
            stem = png.stem
            label = stem.replace("-", " ").replace("_", " ")
            screenshots.append({"path": f"screenshots/{png.name}", "label": label})

    new_round = {
        "metrics": read_json(pack_dir / "metrics.json"),
        "patterns": read_json(pack_dir / "patterns.json"),
        "analysis": read_json(pack_dir / "analysis.json"),
        "testResults": read_json(pack_dir / "test-results.json"),
        "tools": read_json(pack_dir / "tools.json"),
        "screenshots": screenshots,
        "gitBranch": git_branch,
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    rounds = list(prev_data.get("rounds") or []) + [new_round]

    data = {
        "sessionId": session_id,
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rounds": rounds,
        "transcript": [],
    }

    transcript_jsonl = pack_dir / "transcript.jsonl"
    if transcript_jsonl.is_file():
        data["transcript"] = load_jsonl(transcript_jsonl)

    (pack_dir / "data.json").write_text(json.dumps(data, indent=2), encoding="utf-8")

    if transcript_jsonl.is_file():
        render_transcript_html(transcript_jsonl, pack_dir)

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
    (pack_dir / "data.json").write_text(json.dumps(data_no_transcript, indent=2), encoding="utf-8")

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for f in pack_dir.rglob("*"):
            if f.is_file() and f.suffix != ".jsonl":
                zf.write(f, f"{session_id}/{f.relative_to(pack_dir)}")

    shutil.rmtree(pack_dir)
    print(f"Eval pack rendered to {zip_path}")


if __name__ == "__main__":
    main()
