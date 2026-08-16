"""Resolve a lens's declared transcript view from its .md frontmatter. Stdlib regex only.

A lens declares, in YAML frontmatter:  inputs: { transcript: conversation }
or the block form:                     inputs:
                                         transcript: conversation
Absent / unknown -> "full" (fail-safe: a lens is never silently starved)."""
import re
from pathlib import Path

import transcript_views

_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
# matches `transcript: <word>` on its own line (block form) OR inside `inputs: { transcript: <word> }`
_TRANSCRIPT = re.compile(r"transcript\s*:\s*([A-Za-z0-9_-]+)")
_INPUTS_LINE = re.compile(r"^(\s*)inputs\s*:(.*)$")


def _inputs_mapping_text(front):
    """Return only the text that belongs to the `inputs:` mapping — its inline
    remainder for `inputs: { ... }`, or its more-indented block-form children.
    Structurally scoping the search here (rather than searching all of `front`
    for `transcript:`) prevents a `transcript:` occurring elsewhere in the
    frontmatter (e.g. inside an unrelated value or comment) from misfiring."""
    lines = front.splitlines()
    for i, line in enumerate(lines):
        m = _INPUTS_LINE.match(line)
        if not m:
            continue
        indent, remainder = m.group(1), m.group(2)
        if remainder.strip():
            return remainder  # inline form: inputs: { transcript: activity }
        block_lines = []
        for nxt in lines[i + 1:]:
            if not nxt.strip():
                continue
            if (len(nxt) - len(nxt.lstrip())) <= len(indent):
                break
            block_lines.append(nxt)
        return "\n".join(block_lines)
    return ""


def declared_view(md_text):
    m = _FRONTMATTER.search(md_text or "")
    if not m:
        return "full"
    front = m.group(1)
    scoped = _inputs_mapping_text(front)
    if not scoped:
        return "full"
    t = _TRANSCRIPT.search(scoped)
    if not t:
        return "full"
    view = t.group(1)
    return view if view in transcript_views.VIEWS else "full"


def requested_views(lens_dir, lens_skills):
    lens_dir = Path(lens_dir)
    views = set()
    for skill in lens_skills:
        md = lens_dir / (skill + ".md")
        if md.is_file():
            views.add(declared_view(md.read_text(encoding="utf-8")))
        else:
            views.add("full")
    return views


if __name__ == "__main__":
    import json as _json, sys as _sys
    lens_dir, cfg_path = _sys.argv[1], _sys.argv[2]
    cfg = _json.loads(Path(cfg_path).read_text(encoding="utf-8")) if Path(cfg_path).is_file() else {}
    skills = [l.get("skill") for l in (cfg.get("analysisLenses") or []) if l.get("skill")]
    views = requested_views(lens_dir, skills) - {"full"}
    print(" ".join(sorted(views)))
