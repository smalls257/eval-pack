#!/usr/bin/env python3
r"""Single source for lens version metadata + the content-hash used by the drift gate.

Both the gate test and assemble_lenses import from here so the hash function and lock
location can never drift apart.
"""
import hashlib
import json
from pathlib import Path

LENS_DIR = Path(__file__).resolve().parent.parent / "agents" / "lenses"
LOCK_PATH = LENS_DIR / "lens-versions.json"


def md_hash(text):
    r"""Stable sha256 of a lens definition: newlines normalized to '\n', utf-8.
    Normalizing line endings keeps the hash identical across OSes (no spurious Windows red)."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def hash_file(path):
    return md_hash(Path(path).read_text(encoding="utf-8"))


def load_lock():
    """The checked-in {skill: {version, sha256}} map; {} if unreadable."""
    try:
        return json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def version_for(skill):
    """Locked version for a first-party lens, or None."""
    return (load_lock().get(skill) or {}).get("version")
