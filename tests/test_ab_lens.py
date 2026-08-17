import json
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
AB_LENS = SCRIPTS / "ab_lens.py"

RECORDS = [
    {"turnId": 1, "type": "assistant",
     "message": {"role": "assistant", "content": [
         {"type": "text", "text": "hello"},
         {"type": "tool_use", "name": "Bash", "input": {"command": "pytest"}}]}},
    {"turnId": 2, "type": "user",
     "message": {"role": "user", "content": [
         {"type": "tool_result", "content": "X" * 500}]}},
]


def test_ab_lens_smoke(tmp_path):
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text("\n".join(json.dumps(r) for r in RECORDS) + "\n")
    out_dir = tmp_path / "views"

    result = subprocess.run(
        [sys.executable, str(AB_LENS), str(transcript), str(out_dir)],
        capture_output=True, text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "SKEL" in result.stdout
    assert (out_dir / "skeleton.jsonl").is_file()
