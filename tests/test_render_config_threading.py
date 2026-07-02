import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import render_html  # noqa: E402


def _skill_line(arg_len):
    return json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Skill", "id": "s1",
         "input": {"skill": "demo", "args": "x" * arg_len}}
    ]}})


class TestLoadRoundInputsThreadsConfig(unittest.TestCase):
    def test_extract_tools_rerun_honors_config(self):
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d)
            (pack / "transcript.jsonl").write_text(_skill_line(50) + "\n", encoding="utf-8")
            cfg_path = pack / "eval-config.json"
            cfg_path.write_text(json.dumps({"skillArgsMaxLen": 10}), encoding="utf-8")
            (pack / "analysis.json").write_text(json.dumps({"title": "t"}), encoding="utf-8")
            render_html.load_round_inputs(pack, pack / "transcript.jsonl", SCRIPTS)
            tools = json.loads((pack / "tools.json").read_text(encoding="utf-8"))
            self.assertEqual(len(tools["skills"][0]["args"]), 10,
                             "re-run of extract_tools must pass --config, not clobber with defaults")


if __name__ == "__main__":
    unittest.main()
