import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import merge_sessions  # noqa: E402


def _write(path, entries):
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")


class MergeTests(unittest.TestCase):
    def test_dedups_by_uuid_and_orders_by_timestamp(self):
        with tempfile.TemporaryDirectory() as d:
            a = Path(d) / "a.jsonl"
            b = Path(d) / "b.jsonl"
            _write(a, [
                {"uuid": "u1", "timestamp": "2026-06-01T10:00:00Z", "v": "a1"},
                {"uuid": "u2", "timestamp": "2026-06-01T12:00:00Z", "v": "a2"},
            ])
            _write(b, [
                {"uuid": "u2", "timestamp": "2026-06-01T12:00:00Z", "v": "dup"},
                {"uuid": "u3", "timestamp": "2026-06-01T11:00:00Z", "v": "b1"},
            ])
            merged = merge_sessions.merge([a, b])
            self.assertEqual([e["uuid"] for e in merged], ["u1", "u3", "u2"])
            self.assertEqual(
                next(e for e in merged if e["uuid"] == "u2")["v"], "a2")

    def test_keeps_entries_without_uuid(self):
        with tempfile.TemporaryDirectory() as d:
            a = Path(d) / "a.jsonl"
            _write(a, [{"type": "permission-mode"}, {"uuid": "u1", "timestamp": "z"}])
            merged = merge_sessions.merge([a])
            self.assertEqual(len(merged), 2)

    def test_write_merged_roundtrips(self):
        with tempfile.TemporaryDirectory() as d:
            a = Path(d) / "a.jsonl"
            out = Path(d) / "merged.jsonl"
            _write(a, [{"uuid": "u1", "timestamp": "t"}])
            n = merge_sessions.write_merged([a], out)
            self.assertEqual(n, 1)
            lines = [json.loads(l) for l in out.read_text().splitlines() if l.strip()]
            self.assertEqual(lines[0]["uuid"], "u1")

    def test_missing_file_is_skipped_not_fatal(self):
        with tempfile.TemporaryDirectory() as d:
            a = Path(d) / "a.jsonl"
            _write(a, [{"uuid": "u1", "timestamp": "t"}])
            merged = merge_sessions.merge([Path(d) / "missing.jsonl", a])
            self.assertEqual([e["uuid"] for e in merged], ["u1"])


if __name__ == "__main__":
    unittest.main()
