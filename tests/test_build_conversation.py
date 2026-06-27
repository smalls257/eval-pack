import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import build_conversation  # noqa: E402


def _write(path, entries):
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")


class BuildConversationTests(unittest.TestCase):
    def test_current_plus_selected_merge(self):
        with tempfile.TemporaryDirectory() as d:
            current = Path(d) / "cur.jsonl"
            _write(current, [{"uuid": "c1", "timestamp": "2026-06-03T00:00:00Z"}])
            picked = Path(d) / "picked.jsonl"
            _write(picked, [{"uuid": "p1", "timestamp": "2026-06-01T00:00:00Z"}])
            out = Path(d) / "merged.jsonl"
            res = build_conversation.build(
                str(current), "curid", out, selected_paths=[str(picked)])
            self.assertEqual(res["sessions"], 2)
            uuids = [json.loads(l)["uuid"]
                     for l in out.read_text().splitlines() if l.strip()]
            self.assertEqual(uuids, ["p1", "c1"])

    def test_current_only_when_no_selection(self):
        with tempfile.TemporaryDirectory() as d:
            current = Path(d) / "cur.jsonl"
            _write(current, [{"uuid": "c1", "timestamp": "t"}])
            out = Path(d) / "merged.jsonl"
            res = build_conversation.build(str(current), "curid", out)
            self.assertEqual(res["sessions"], 1)
            self.assertEqual(res["entries"], 1)

    def test_subagents_of_selected_are_folded_in(self):
        with tempfile.TemporaryDirectory() as d:
            current = Path(d) / "cur.jsonl"
            _write(current, [{"uuid": "c1", "timestamp": "2026-06-03T00:00:00Z"}])
            picked = Path(d) / "picked.jsonl"
            _write(picked, [{"uuid": "p1", "timestamp": "2026-06-01T00:00:00Z"}])
            sub = Path(d) / "picked" / "subagents"
            sub.mkdir(parents=True)
            _write(sub / "agent-1.jsonl",
                   [{"uuid": "sa1", "timestamp": "2026-06-01T00:30:00Z"}])
            out = Path(d) / "merged.jsonl"
            res = build_conversation.build(
                str(current), "curid", out, selected_paths=[str(picked)])
            uuids = [json.loads(l)["uuid"]
                     for l in out.read_text().splitlines() if l.strip()]
            self.assertEqual(uuids, ["p1", "sa1", "c1"])

    def test_no_double_count_selected_equals_current(self):
        with tempfile.TemporaryDirectory() as d:
            current = Path(d) / "cur.jsonl"
            _write(current, [{"uuid": "c1", "timestamp": "t"}])
            out = Path(d) / "merged.jsonl"
            res = build_conversation.build(
                str(current), "curid", out, selected_paths=[str(current)])
            self.assertEqual(res["sessions"], 1)

    def test_zero_when_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "merged.jsonl"
            res = build_conversation.build("", "curid", out)
            self.assertEqual(res["sessions"], 0)
            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
