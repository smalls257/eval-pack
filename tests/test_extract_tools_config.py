# tests/test_extract_tools_config.py
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _transcript_with_long_skill_args(path, arg_len):
    line = {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Skill", "id": "s1",
         "input": {"skill": "demo", "args": "x" * arg_len}}
    ]}}
    path.write_text(json.dumps(line) + "\n", encoding="utf-8")


class TestSkillArgsMaxLen(unittest.TestCase):
    def test_config_truncation_length_applied(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as pack:
            tpath = Path(d) / "transcript.jsonl"
            _transcript_with_long_skill_args(tpath, 50)
            cfg_path = Path(d) / "eval-config.json"
            cfg_path.write_text(json.dumps({"skillArgsMaxLen": 10}), encoding="utf-8")

            subprocess.run(
                [sys.executable, str(SCRIPTS / "extract_tools.py"),
                 str(tpath), pack, "--config", str(cfg_path)],
                check=True, capture_output=True, text=True,
            )
            tools = json.loads((Path(pack) / "tools.json").read_text())
            self.assertEqual(len(tools["skills"][0]["args"]), 10)


if __name__ == "__main__":
    unittest.main()
