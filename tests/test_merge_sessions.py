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

    def test_malformed_line_skipped_but_valid_kept(self):
        with tempfile.TemporaryDirectory() as d:
            a = Path(d) / "a.jsonl"
            a.write_text(
                '{"uuid":"u1","timestamp":"t"}\nNOT JSON\n{"uuid":"u2","timestamp":"u"}\n',
                encoding="utf-8")
            merged = merge_sessions.merge([a])
            self.assertEqual([e["uuid"] for e in merged], ["u1", "u2"])


def test_merge_assigns_monotonic_turnid(tmp_path):
    p = tmp_path / "s.jsonl"
    p.write_text(
        '{"uuid":"b","timestamp":"2026-01-01T00:00:02Z","type":"assistant"}\n'
        '{"uuid":"a","timestamp":"2026-01-01T00:00:01Z","type":"user"}\n',
        encoding="utf-8",
    )
    entries = merge_sessions.merge([p])
    # sorted by timestamp: a then b
    assert [e["turnId"] for e in entries] == [0, 1]
    assert [e["uuid"] for e in entries] == ["a", "b"]

def test_turnid_is_assigned_after_sort_even_without_timestamps(tmp_path):
    p = tmp_path / "s.jsonl"
    p.write_text(
        '{"uuid":"x","type":"user"}\n{"uuid":"y","type":"assistant"}\n',
        encoding="utf-8",
    )
    entries = merge_sessions.merge([p])
    assert [e["turnId"] for e in entries] == [0, 1]


if __name__ == "__main__":
    unittest.main()
