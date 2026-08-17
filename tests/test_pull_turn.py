import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import pull_turn  # noqa: E402


def _t(tmp_path):
    p = tmp_path / "transcript.jsonl"
    p.write_text(
        '{"turnId":5,"type":"assistant","message":{"role":"assistant","content":['
        '{"type":"thinking","thinking":"secret plan"},'
        '{"type":"text","text":"done"},'
        '{"type":"tool_use","name":"Bash","input":{"command":"pytest"}}]}}\n'
        '{"turnId":6,"type":"user","message":{"role":"user","content":['
        '{"type":"tool_result","content":"FULL LOG line1\\n...5000 chars...\\nFAILED"}]}}\n',
        encoding="utf-8")
    return p


class TestPullTurn(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_pull_tool_result_returns_full_body(self):
        p = _t(self.tmp)
        assert "FULL LOG line1" in pull_turn.pull(p, 6, field="tool_result")
        assert "FAILED" in pull_turn.pull(p, 6, field="tool_result")

    def test_pull_thinking_and_text(self):
        p = _t(self.tmp)
        assert "secret plan" in pull_turn.pull(p, 5, field="thinking")
        assert "done" in pull_turn.pull(p, 5, field="text")

    def test_unknown_turn_raises(self):
        p = _t(self.tmp)
        with self.assertRaises(KeyError):
            pull_turn.pull(p, 99, field="text")

    def test_cli_unknown_turn_exits_2(self):
        p = _t(self.tmp)
        r = subprocess.run([sys.executable, str(SCRIPTS/"pull_turn.py"), str(p), "99", "--field", "text"],
                           capture_output=True, text=True)
        assert r.returncode == 2 and r.stderr.strip()

    def test_cli_prints_body(self):
        p = _t(self.tmp)
        r = subprocess.run([sys.executable, str(SCRIPTS/"pull_turn.py"), str(p), "6", "--field", "tool_result"],
                           capture_output=True, text=True)
        assert r.returncode == 0 and "FAILED" in r.stdout

    def test_cli_missing_transcript_exits_2(self):
        missing = self.tmp / "does-not-exist.jsonl"
        r = subprocess.run([sys.executable, str(SCRIPTS/"pull_turn.py"), str(missing), "6", "--field", "text"],
                           capture_output=True, text=True)
        assert r.returncode == 2 and r.stderr.strip()

    def test_pull_batch_one_scan_returns_each(self):
        p = _t(self.tmp)   # existing fixture with turnId 5 (assistant) + 6 (tool_result)
        got = pull_turn.pull_batch(p, [5, 6], field="text")
        assert "done" in got[5]                 # turn 5 text
        assert 6 in got                         # turn 6 present (empty text ok)

    def test_pull_batch_reports_missing(self):
        p = _t(self.tmp)
        got = pull_turn.pull_batch(p, [6, 99], field="tool_result")
        assert 6 in got and 99 not in got       # 99 absent, not fabricated

    def test_pull_batch_all_missing_returns_empty(self):
        p = _t(self.tmp)
        got = pull_turn.pull_batch(p, [98, 99], field="text")
        assert got == {}

    def test_cli_ids_labeled_output(self):
        p = _t(self.tmp)
        r = subprocess.run([sys.executable, str(SCRIPTS/"pull_turn.py"), str(p),
                            "--ids", "5,6", "--field", "text"], capture_output=True, text=True)
        assert r.returncode == 0
        assert '"5"' in r.stdout and '"6"' in r.stdout   # JSON-object output keyed by id
        parsed = json.loads(r.stdout)
        assert "done" in parsed["5"]

    def test_cli_ids_partial_hit_is_success(self):
        p = _t(self.tmp)
        r = subprocess.run([sys.executable, str(SCRIPTS/"pull_turn.py"), str(p),
                            "--ids", "6,99", "--field", "tool_result"], capture_output=True, text=True)
        assert r.returncode == 0
        parsed = json.loads(r.stdout)
        assert "6" in parsed and "99" not in parsed
        assert "99" in r.stderr

    def test_cli_ids_all_missing_exits_nonzero(self):
        p = _t(self.tmp)
        r = subprocess.run([sys.executable, str(SCRIPTS/"pull_turn.py"), str(p),
                            "--ids", "98,99", "--field", "text"], capture_output=True, text=True)
        assert r.returncode != 0
        assert "98" in r.stderr and "99" in r.stderr

    def test_cli_ids_and_positional_turn_id_mutually_exclusive(self):
        p = _t(self.tmp)
        r = subprocess.run([sys.executable, str(SCRIPTS/"pull_turn.py"), str(p), "5",
                            "--ids", "5,6", "--field", "text"], capture_output=True, text=True)
        assert r.returncode != 0


if __name__ == "__main__":
    unittest.main()
