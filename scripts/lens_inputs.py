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
_INPUTS_PRESENT = re.compile(r"^\s*inputs\s*:", re.MULTILINE)


def declared_view(md_text):
    m = _FRONTMATTER.search(md_text or "")
    if not m:
        return "full"
    front = m.group(1)
    if not _INPUTS_PRESENT.search(front):
        return "full"
    t = _TRANSCRIPT.search(front)
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
