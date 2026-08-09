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

    def test_non_evidential_finding_cannot_justify_escalation(self):
        rules = [{"when": {"level": {"min": "medium"}},
                  "require": {"findings.types": {"at_least_one_in": ["capitulation", "drift"]}}}]
        out = {"level": "high", "findings": [{"type": "capitulation", "evidential": False}]}
        passed, msgs = lens_checks.rule_consistency(out, rules, ORD)
        self.assertFalse(passed)
        self.assertTrue(msgs)

        evidential_out = {"level": "high", "findings": [{"type": "capitulation", "evidential": True}]}
        self.assertEqual(lens_checks.rule_consistency(evidential_out, rules, ORD), (True, []))

if __name__ == "__main__":
    unittest.main()
