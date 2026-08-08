# tests/test_extract_metrics_config.py
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _transcript(path):
    lines = [
        {"type": "assistant", "message": {"model": "m1", "usage": {
            "input_tokens": 10, "output_tokens": 20,
            "cache_read_input_tokens": 30, "cache_creation_input_tokens": 40},
            "content": [{"type": "text", "text": "hi"}]}},
    ]
    path.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")


def _run(tpath, pack, cfg_path=None):
    args = [sys.executable, str(SCRIPTS / "extract_metrics.py"), str(tpath), str(pack)]
    if cfg_path:
        args += ["--config", str(cfg_path)]
    subprocess.run(args, check=True, capture_output=True, text=True)
    return json.loads((Path(pack) / "metrics.json").read_text(encoding="utf-8"))


class TestTotalTokens(unittest.TestCase):
    def test_plain_unweighted_sum(self):
        # totalTokens is a plain factual sum — no config-driven weighting.
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as pack:
            t = Path(d) / "t.jsonl"
            _transcript(t)
            m = _run(t, pack)
            self.assertEqual(m["totalTokens"], 100)  # 10+20+30+40


if __name__ == "__main__":
    unittest.main()
