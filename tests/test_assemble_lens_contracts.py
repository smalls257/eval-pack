# tests/test_assemble_lens_contracts.py
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import assemble_lenses  # noqa: E402

class TestAssembleContracts(unittest.TestCase):
    def test_conforming_scorer_passes(self):
        # requirement-drift declares gradedField score + findingTypes; a conforming result survives
        r = {"skill": "requirement-drift", "role": "scorer", "score": 90,
             "findings": [{"type": "met", "quote": "x", "evidential": True, "detail": "d"}]}
        out = assemble_lenses.validate_lens_contracts([r])
        self.assertNotIn("error", out[0])

    def test_violating_scorer_becomes_failure(self):
        # score out of range violates requirement-drift's contract
        r = {"skill": "requirement-drift", "role": "scorer", "score": 900, "findings": []}
        out = assemble_lenses.validate_lens_contracts([r])
        self.assertIn("error", out[0])
        self.assertIn("contract violation", out[0]["error"])

    def test_lens_without_contract_passes_through(self):
        # 'friction' has no output block (out of Part-2 scope) -> unchanged
        r = {"skill": "friction", "role": "contributor", "entries": []}
        out = assemble_lenses.validate_lens_contracts([r])
        self.assertNotIn("error", out[0])

    def test_already_errored_result_untouched(self):
        r = {"skill": "requirement-drift", "role": "scorer", "error": "malformed"}
        out = assemble_lenses.validate_lens_contracts([r])
        self.assertEqual(out[0]["error"], "malformed")

if __name__ == "__main__":
    unittest.main()
