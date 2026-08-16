import json, subprocess, sys
from pathlib import Path
SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import pull_turn

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

def test_pull_tool_result_returns_full_body(tmp_path):
    p = _t(tmp_path)
    assert "FULL LOG line1" in pull_turn.pull(p, 6, field="tool_result")
    assert "FAILED" in pull_turn.pull(p, 6, field="tool_result")

def test_pull_thinking_and_text(tmp_path):
    p = _t(tmp_path)
    assert "secret plan" in pull_turn.pull(p, 5, field="thinking")
    assert "done" in pull_turn.pull(p, 5, field="text")

def test_unknown_turn_raises(tmp_path):
    p = _t(tmp_path)
    import pytest
    with pytest.raises(KeyError):
        pull_turn.pull(p, 99, field="text")

def test_cli_unknown_turn_exits_2(tmp_path):
    p = _t(tmp_path)
    r = subprocess.run([sys.executable, str(SCRIPTS/"pull_turn.py"), str(p), "99", "--field", "text"],
                       capture_output=True, text=True)
    assert r.returncode == 2 and r.stderr.strip()

def test_cli_prints_body(tmp_path):
    p = _t(tmp_path)
    r = subprocess.run([sys.executable, str(SCRIPTS/"pull_turn.py"), str(p), "6", "--field", "tool_result"],
                       capture_output=True, text=True)
    assert r.returncode == 0 and "FAILED" in r.stdout

def test_cli_missing_transcript_exits_2(tmp_path):
    missing = tmp_path / "does-not-exist.jsonl"
    r = subprocess.run([sys.executable, str(SCRIPTS/"pull_turn.py"), str(missing), "6", "--field", "text"],
                       capture_output=True, text=True)
    assert r.returncode == 2 and r.stderr.strip()
