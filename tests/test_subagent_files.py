import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import build_conversation  # noqa: E402


class SubagentFilesTests(unittest.TestCase):
    def test_finds_subagent_jsonl_beside_transcript(self):
        with tempfile.TemporaryDirectory() as d:
            tr = Path(d) / "sess.jsonl"
            tr.write_text("{}\n", encoding="utf-8")
            sub = Path(d) / "sess" / "subagents"
            sub.mkdir(parents=True)
            (sub / "agent-1.jsonl").write_text("{}\n", encoding="utf-8")
            (sub / "agent-2.jsonl").write_text("{}\n", encoding="utf-8")
            names = sorted(p.name for p in build_conversation.subagent_files(tr))
            self.assertEqual(names, ["agent-1.jsonl", "agent-2.jsonl"])

    def test_empty_when_no_subagents_dir(self):
        with tempfile.TemporaryDirectory() as d:
            tr = Path(d) / "sess.jsonl"
            tr.write_text("{}\n", encoding="utf-8")
            self.assertEqual(build_conversation.subagent_files(tr), [])
