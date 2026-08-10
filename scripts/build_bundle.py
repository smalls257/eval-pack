"""Write a committed eval-pack fixture directory from normalized parts. Stdlib only."""
import json
from pathlib import Path


def write_fixture(fixture_dir, transcript_lines, meta, base_files=None, delivered_patch=None):
    fixture_dir = Path(fixture_dir)
    fixture_dir.mkdir(parents=True, exist_ok=True)
    with (fixture_dir / "transcript.jsonl").open("w", encoding="utf-8") as f:
        for line in transcript_lines:
            f.write(json.dumps(line) + "\n")
    (fixture_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    if base_files and delivered_patch is not None:
        for relpath, content in base_files.items():
            dest = fixture_dir / "base" / relpath
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
        (fixture_dir / "delivered.patch").write_text(delivered_patch, encoding="utf-8")
