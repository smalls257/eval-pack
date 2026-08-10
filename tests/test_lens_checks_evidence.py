# tests/test_lens_checks_evidence.py
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import lens_checks  # noqa: E402

CORPUS = "user: Are you sure?\nassistant: You are right to question my answer!"

class TestEvidence(unittest.TestCase):
    def test_resolvable_quote_passes(self):
        out = {"findings": [{"type": "capitulation", "quote": "You are right to question", "evidential": True}]}
        self.assertEqual(lens_checks.evidence_resolution(out, CORPUS), (True, []))

    def test_hallucinated_quote_fails(self):
        out = {"findings": [{"type": "capitulation", "quote": "I never said this", "evidential": True}]}
        passed, msgs = lens_checks.evidence_resolution(out, CORPUS)
        self.assertFalse(passed)
        self.assertTrue(msgs)

    def test_nonevidential_finding_skipped(self):
        out = {"findings": [{"type": "praise", "quote": None, "evidential": False}]}
        self.assertEqual(lens_checks.evidence_resolution(out, CORPUS), (True, []))

    def test_whitespace_normalized_match(self):
        out = {"findings": [{"type": "capitulation", "quote": "Are   you\nsure?", "evidential": True}]}
        self.assertTrue(lens_checks.evidence_resolution(out, CORPUS)[0])

if __name__ == "__main__":
    unittest.main()
