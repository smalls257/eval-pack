import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import render_html  # noqa: E402


def _pack(d, *, transcript=None, metrics=None):
    p = Path(d)
    if transcript is not None:
        (p / "transcript.jsonl").write_text(
            "\n".join(json.dumps(e) for e in transcript) + ("\n" if transcript else ""),
            encoding="utf-8")
    if metrics is not None:
        (p / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
    return p


_GOOD_TURNS = [
    {"type": "user", "message": {"content": "hi"}},
    {"type": "assistant", "message": {"content": [{"type": "text", "text": "ok"}]}},
]


class ValidatePackTests(unittest.TestCase):
    def test_complete_pack_has_no_gaps(self):
        with tempfile.TemporaryDirectory() as d:
            _pack(d, transcript=_GOOD_TURNS, metrics={"turnCount": 2})
            self.assertEqual(render_html.validate_pack(Path(d)), [])

    def test_missing_transcript_is_a_gap(self):
        with tempfile.TemporaryDirectory() as d:
            _pack(d, metrics={"turnCount": 2})
            gaps = render_html.validate_pack(Path(d))
            self.assertTrue(any("transcript" in g for g in gaps))

    def test_empty_transcript_is_a_gap(self):
        with tempfile.TemporaryDirectory() as d:
            _pack(d, transcript=[], metrics={"turnCount": 2})
            self.assertTrue(any("transcript" in g for g in render_html.validate_pack(Path(d))))

    def test_transcript_without_turns_is_a_gap(self):
        with tempfile.TemporaryDirectory() as d:
            _pack(d, transcript=[{"type": "permission-mode"}, {"type": "summary"}],
                  metrics={"turnCount": 2})
            self.assertTrue(any("no conversation turns" in g
                                for g in render_html.validate_pack(Path(d))))

    def test_missing_or_empty_metrics_is_a_gap(self):
        with tempfile.TemporaryDirectory() as d:
            _pack(d, transcript=_GOOD_TURNS, metrics={})  # backfilled empty
            self.assertTrue(any("metrics" in g for g in render_html.validate_pack(Path(d))))


if __name__ == "__main__":
    unittest.main()
