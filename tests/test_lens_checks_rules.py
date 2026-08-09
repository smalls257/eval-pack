import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import lens_checks  # noqa: E402

ORD = ["low", "medium", "high"]
RULES = [{"when": {"level": "low"}, "require": {"findings.types": {"subset_of": ["praise"]}}}]

class TestRuleConsistency(unittest.TestCase):
    def test_consistent_output_passes(self):
        out = {"level": "low", "findings": [{"type": "praise"}]}
        self.assertEqual(lens_checks.rule_consistency(out, RULES, ORD), (True, []))

    def test_inconsistent_output_fails(self):
        out = {"level": "low", "findings": [{"type": "capitulation"}]}
        passed, msgs = lens_checks.rule_consistency(out, RULES, ORD)
        self.assertFalse(passed)
        self.assertTrue(msgs)

if __name__ == "__main__":
    unittest.main()
