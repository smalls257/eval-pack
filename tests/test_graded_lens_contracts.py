# tests/test_graded_lens_contracts.py
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import lens_manifest  # noqa: E402

LENS_DIR = Path(__file__).resolve().parent.parent / "agents" / "lenses"
GRADED = {
    "requirement-drift": ("score", None, ["unmet", "unrequested", "met"]),
    "verification-rigor": ("score", None, None),
    "sycophancy": ("level", ["low", "medium", "high"],
                   ["capitulation", "false-belief", "compound", "drift", "praise", "one-sided-flag"]),
    "business-risk": ("level", ["low", "medium", "high"], None),
    "user-improvements": ("level", ["low", "medium", "high"], ["strength", "improvement"]),
}

class TestGradedLensContracts(unittest.TestCase):
    def test_each_graded_lens_declares_expected_contract(self):
        for name, (gf, ordinal, ftypes) in GRADED.items():
            md = (LENS_DIR / (name + ".md")).read_text(encoding="utf-8")
            c = lens_manifest.find_output_contract(md)
            self.assertIsNotNone(c, name + " has no output contract")
            self.assertEqual(c["gradedField"], gf, name)
            self.assertEqual(c.get("levelOrdinal"), ordinal, name)
            self.assertEqual(c.get("findingTypes"), ftypes, name)

    def test_drift_and_syco_findings_schema_has_quote_and_evidential(self):
        for name in ("requirement-drift", "sycophancy"):
            md = (LENS_DIR / (name + ".md")).read_text(encoding="utf-8")
            self.assertIn('"quote"', md, name + " findings schema missing quote")
            self.assertIn('"evidential"', md, name + " findings schema missing evidential")

    def test_user_improvements_declares_items_adapter_contract(self):
        md = (LENS_DIR / "user-improvements.md").read_text(encoding="utf-8")
        c = lens_manifest.find_output_contract(md)
        self.assertEqual(c["gradedField"], "level")
        self.assertEqual(c["findingsKey"], "items")
        self.assertEqual(c["typeField"], "kind")
        self.assertEqual(c["findingTypes"], ["strength", "improvement"])
        self.assertIn('"quote"', md)
        self.assertIn('"evidential"', md)

if __name__ == "__main__":
    unittest.main()
