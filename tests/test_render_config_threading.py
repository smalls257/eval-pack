import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
PLUGIN_ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))
import render_html  # noqa: E402
import config  # noqa: E402


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


def _make_pack(out_dir, sid, pack_cost=None):
    pack = Path(out_dir) / sid
    pack.mkdir(parents=True)
    base = dict(json.loads(json.dumps(config.DEFAULTS)))
    (pack / "eval-config.json").write_text(json.dumps(base), encoding="utf-8")
    (pack / "transcript.jsonl").write_text(json.dumps(
        {"type": "assistant", "message": {"content": "hi"}}) + "\n", encoding="utf-8")
    (pack / "metrics.json").write_text(json.dumps({"turnCount": 1}), encoding="utf-8")
    (pack / "analysis.json").write_text(json.dumps({"title": "t"}), encoding="utf-8")
    (pack / "patterns.json").write_text(json.dumps({"flags": []}), encoding="utf-8")
    (pack / "test-results.json").write_text(json.dumps({"verdict": "none"}), encoding="utf-8")
    if pack_cost is not None:
        (pack / "pack-cost.json").write_text(json.dumps(pack_cost), encoding="utf-8")
    return pack


def _render(out_dir, sid, pack):
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "render_html.py"), str(out_dir), sid,
         str(PLUGIN_ROOT), str(pack / "transcript.jsonl"), "--branch", sid],
        capture_output=True, text=True)


class TestPackCostThreading(unittest.TestCase):
    """pack-cost.json (Task 1/2's cost ledger) must reach the rendered data dict as
    `packCost` — and a missing ledger (old packs, pre-cost-ledger) must not crash render."""

    def test_pack_cost_threaded_when_present(self):
        pack_cost = {
            "perLens": [
                {"skill": "sycophancy", "tokens": 44155, "model": "sonnet", "reused": False},
                {"skill": "friction", "tokens": None, "gap": "unreadable sidecar", "model": None, "reused": None},
            ],
            "evaluatorTokens": 51000,
            "totalTokens": 220000,
            "gaps": ["friction"],
        }
        with tempfile.TemporaryDirectory() as out:
            pack = _make_pack(out, "withcost", pack_cost=pack_cost)
            r = _render(out, "withcost", pack)
            self.assertEqual(r.returncode, 0, r.stderr)
            data = json.loads((pack / "data.json").read_text(encoding="utf-8"))
            self.assertEqual(data["packCost"], pack_cost)

    def test_render_does_not_crash_when_pack_cost_absent(self):
        with tempfile.TemporaryDirectory() as out:
            pack = _make_pack(out, "nocost", pack_cost=None)
            self.assertFalse((pack / "pack-cost.json").exists())
            r = _render(out, "nocost", pack)
            self.assertEqual(r.returncode, 0, r.stderr)
            data = json.loads((pack / "data.json").read_text(encoding="utf-8"))
            self.assertIn("packCost", data)
            # read_json's no-default path returns {} for a missing file — assert that,
            # not just "falsy", so a future change to the empty-default can't silently pass.
            self.assertEqual(data["packCost"], {})


if __name__ == "__main__":
    unittest.main()
