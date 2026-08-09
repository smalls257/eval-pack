# tests/test_lens_checks_adapter.py
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import lens_checks  # noqa: E402

CORPUS = "user: Are you sure the HTML is the issue?\nassistant: you are right"
ORD = ["low", "medium", "high"]

class TestChecksAdapter(unittest.TestCase):
    def test_evidence_resolution_over_items(self):
        out = {"items": [{"kind": "strength", "quote": "Are you sure the HTML is the issue", "evidential": True}]}
        self.assertEqual(lens_checks.evidence_resolution(out, CORPUS, findings_key="items"), (True, []))
        bad = {"items": [{"kind": "strength", "quote": "never said this", "evidential": True}]}
        self.assertFalse(lens_checks.evidence_resolution(bad, CORPUS, findings_key="items")[0])

    def test_assert_one_findings_over_items(self):
        out = {"level": "high", "items": [{"kind": "strength"}]}
        gold = {"level": {"min": "medium"}, "findings": {"include": ["strength"]}}
        self.assertTrue(lens_checks.assert_one(out, gold, ORD, findings_key="items"))

    def test_defaults_unchanged(self):
        out = {"findings": [{"type": "capitulation", "quote": "x", "evidential": True}]}
        self.assertEqual(lens_checks.evidence_resolution(out, "x"), (True, []))
        self.assertTrue(lens_checks.assert_one({"score": 90}, {"score": {"min": 70, "max": 100}}, ORD))

if __name__ == "__main__":
    unittest.main()
