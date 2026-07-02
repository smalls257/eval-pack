# tests/test_extract_metrics_config.py
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import config  # noqa: E402


def _transcript(path):
    lines = [
        {"type": "assistant", "message": {"model": "m1", "usage": {
            "input_tokens": 10, "output_tokens": 20,
            "cache_read_input_tokens": 30, "cache_creation_input_tokens": 40},
            "content": [{"type": "text", "text": "hi"}]}},
    ]
    path.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")


def _write_cfg(path, overrides):
    # read_config() consumes an already-resolved eval-config.json (no merging),
    # so fixtures must write DEFAULTS + override, as resolve_config.py would.
    base = json.loads(json.dumps(config.DEFAULTS))
    base.update(overrides)
    path.write_text(json.dumps(base), encoding="utf-8")


def _run(tpath, pack, cfg_path=None):
    args = [sys.executable, str(SCRIPTS / "extract_metrics.py"), str(tpath), str(pack)]
    if cfg_path:
        args += ["--config", str(cfg_path)]
    subprocess.run(args, check=True, capture_output=True, text=True)
    return json.loads((Path(pack) / "metrics.json").read_text(encoding="utf-8"))


class TestTokenWeights(unittest.TestCase):
    def test_default_plain_sum(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as pack:
            t = Path(d) / "t.jsonl"
            _transcript(t)
            m = _run(t, pack)
            self.assertEqual(m["totalTokens"], 100)  # 10+20+30+40 — baseline preserved

    def test_weighted_sum(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as pack:
            t = Path(d) / "t.jsonl"
            _transcript(t)
            cfg = Path(d) / "eval-config.json"
            _write_cfg(cfg, {"tokenWeights": {"cacheRead": 0, "cacheWrite": 0}})
            m = _run(t, pack, cfg)
            self.assertEqual(m["totalTokens"], 30)  # 10*1 + 20*1 + 30*0 + 40*0


class TestTokenFieldNames(unittest.TestCase):
    def test_custom_field_name(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as pack:
            t = Path(d) / "t.jsonl"
            lines = [
                {"type": "assistant", "message": {"model": "m1", "content": [
                    {"type": "tool_use", "name": "Agent", "id": "a1", "input": {"model": "m2"}}],
                    "usage": {}}},
                {"type": "user", "message": {"content": [
                    {"type": "tool_result", "tool_use_id": "a1", "content": "my_tokens: 77"}]}},
            ]
            t.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
            cfg = Path(d) / "eval-config.json"
            _write_cfg(cfg, {"tokenFieldNames": ["my_tokens"]})
            m = _run(t, pack, cfg)
            self.assertEqual(m.get("subagentTotalTokens", 0), 77)


if __name__ == "__main__":
    unittest.main()
