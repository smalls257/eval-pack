import json, subprocess, sys, hashlib
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"

def test_cli_emits_requested_views(tmp_path):
    t = tmp_path / "transcript.jsonl"
    t.write_text(
        '{"turnId":0,"type":"user","message":{"role":"user","content":[{"type":"text","text":"hi"}]}}\n'
        '{"turnId":1,"type":"file-history-snapshot","message":{}}\n',
        encoding="utf-8",
    )
    out = tmp_path / "views"
    r = subprocess.run([sys.executable, str(SCRIPTS / "build_views.py"), str(t), str(out),
                        "conversation", "activity"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    conv = (out / "conversation.jsonl").read_text().splitlines()
    header = json.loads(conv[0])
    assert header["_view"] == "conversation"
    assert header["_sourceTranscriptSha256"] == hashlib.sha256(t.read_bytes()).hexdigest()
    assert (out / "activity.jsonl").is_file()
