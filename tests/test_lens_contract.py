# tests/test_lens_contract.py
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import lens_contract  # noqa: E402

SCORE_C = {"gradedField": "score", "findingTypes": ["unmet", "met"]}
LEVEL_C = {"gradedField": "level", "levelOrdinal": ["low", "medium", "high"],
           "findingTypes": ["capitulation", "praise"]}

class TestLensContract(unittest.TestCase):
    def test_valid_score_output(self):
        out = {"score": 90, "findings": [{"type": "met", "quote": "x", "detail": "d"}]}
        self.assertEqual(lens_contract.validate_output(out, SCORE_C), [])

    def test_score_out_of_range(self):
        self.assertTrue(lens_contract.validate_output({"score": 140, "findings": []}, SCORE_C))

    def test_missing_graded_field(self):
        self.assertTrue(lens_contract.validate_output({"findings": []}, SCORE_C))

    def test_undeclared_finding_type(self):
        out = {"level": "high", "findings": [{"type": "bogus", "quote": "x"}]}
        self.assertTrue(lens_contract.validate_output(out, LEVEL_C))

    def test_evidential_finding_missing_quote(self):
        out = {"level": "low", "findings": [{"type": "praise"}]}
        self.assertTrue(lens_contract.validate_output(out, LEVEL_C))

    def test_nonevidential_finding_needs_no_quote(self):
        out = {"level": "low", "findings": [{"type": "praise", "evidential": False}]}
        self.assertEqual(lens_contract.validate_output(out, LEVEL_C), [])

    def test_level_not_in_ordinal(self):
        self.assertTrue(lens_contract.validate_output({"level": "extreme", "findings": []}, LEVEL_C))

    def test_score_rejects_bool(self):
        self.assertTrue(lens_contract.validate_output({"score": True, "findings": []}, SCORE_C))

    def test_findings_unchecked_when_no_findingTypes(self):
        # a contract without findingTypes must not flag findings that lack a 'type'
        c = {"gradedField": "score"}
        out = {"score": 80, "findings": [{"claim": "x", "backed": True, "evidence": "cmd"}]}
        self.assertEqual(lens_contract.validate_output(out, c), [])

    def test_findings_checked_when_findingTypes_present(self):
        c = {"gradedField": "score", "findingTypes": ["met"]}
        out = {"score": 80, "findings": [{"claim": "x"}]}  # no 'type' -> violation
        self.assertTrue(lens_contract.validate_output(out, c))

    def test_adapter_items_kind_contract(self):
        c = {"gradedField": "level", "levelOrdinal": ["low", "medium", "high"],
             "findingsKey": "items", "typeField": "kind", "findingTypes": ["strength", "improvement"]}
        ok = {"level": "high", "items": [{"kind": "strength", "quote": "q", "detail": "d"}]}
        self.assertEqual(lens_contract.validate_output(ok, c), [])
        bad_type = {"level": "high", "items": [{"kind": "bogus", "quote": "q"}]}
        self.assertTrue(lens_contract.validate_output(bad_type, c))
        no_quote = {"level": "high", "items": [{"kind": "strength"}]}  # evidential default -> needs quote
        self.assertTrue(lens_contract.validate_output(no_quote, c))

    def test_defaults_unchanged_for_findings_type(self):
        c = {"gradedField": "score", "findingTypes": ["met"]}
        out = {"score": 80, "findings": [{"type": "met", "quote": "q"}]}
        self.assertEqual(lens_contract.validate_output(out, c), [])

if __name__ == "__main__":
    unittest.main()
