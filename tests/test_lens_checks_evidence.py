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

INDEX = {
    5: {"text": "You are right to question my answer!", "truncated": False},
    6: {"text": "pytest … [truncated] … 3 passed", "truncated": True},
}

def _f(**kw):
    base = {"type": "capitulation", "evidential": True}
    base.update(kw); return {"findings": [base]}

class TestEvidenceTurnId(unittest.TestCase):
    def test_turnid_resolves_against_cited_turn(self):
        out = _f(turnId=5, quote="right to question")
        self.assertTrue(lens_checks.evidence_resolution(out, "", turn_index=INDEX)[0])

    def test_turnid_quote_absent_from_untruncated_turn_fails(self):
        out = _f(turnId=5, quote="never said this")
        ok, msgs = lens_checks.evidence_resolution(out, "", turn_index=INDEX)
        self.assertFalse(ok); self.assertTrue(msgs)

    def test_quote_in_truncated_region_is_unverifiable_not_failure(self):
        out = _f(turnId=6, quote="a span the truncation clipped out")
        ok, msgs = lens_checks.evidence_resolution(out, "", turn_index=INDEX)
        self.assertTrue(ok)          # non-penalizing
        self.assertEqual(msgs, [])

    def test_unknown_turnid_fails(self):
        out = _f(turnId=99, quote="anything")
        self.assertFalse(lens_checks.evidence_resolution(out, "", turn_index=INDEX)[0])

    def test_finding_without_turnid_uses_legacy_corpus(self):
        out = _f(quote="You are right to question")
        corpus = "assistant: You are right to question my answer!"
        self.assertTrue(lens_checks.evidence_resolution(out, corpus)[0])

    def test_require_turn_id_flags_missing(self):
        out = _f(quote="You are right to question")
        corpus = "assistant: You are right to question my answer!"
        ok, msgs = lens_checks.evidence_resolution(out, corpus, require_turn_id=True)
        self.assertFalse(ok)
        self.assertTrue(any("turnId" in m for m in msgs))

if __name__ == "__main__":
    unittest.main()
