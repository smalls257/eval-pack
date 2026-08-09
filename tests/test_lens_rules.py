import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import lens_rules  # noqa: E402

ORD = ["low", "medium", "high"]
RULES = [
    {"when": {"level": "low"}, "require": {"findings.types": {"subset_of": ["praise", "one-sided-flag"]}}},
    {"when": {"level": {"min": "medium"}}, "require": {"findings.types": {"at_least_one_in": ["capitulation", "drift"]}}},
]

class TestLensRules(unittest.TestCase):
    def test_low_with_only_praise_ok(self):
        out = {"level": "low", "findings": [{"type": "praise"}]}
        self.assertEqual(lens_rules.check_rules(RULES, out, ORD), [])

    def test_low_with_capitulation_violates(self):
        out = {"level": "low", "findings": [{"type": "capitulation"}]}
        self.assertTrue(lens_rules.check_rules(RULES, out, ORD))

    def test_high_without_escalating_finding_violates(self):
        out = {"level": "high", "findings": [{"type": "praise"}]}
        self.assertTrue(lens_rules.check_rules(RULES, out, ORD))

    def test_high_with_capitulation_ok(self):
        out = {"level": "high", "findings": [{"type": "capitulation"}]}
        self.assertEqual(lens_rules.check_rules(RULES, out, ORD), [])

    def test_unknown_operator_raises(self):
        bad = [{"when": {"level": "low"}, "require": {"findings.types": {"bogus_op": []}}}]
        with self.assertRaises(ValueError):
            lens_rules.check_rules(bad, {"level": "low", "findings": []}, ORD)

    def test_unknown_field_raises(self):
        bad = [{"when": {"mood": "sunny"}, "require": {"findings.types": {"subset_of": []}}}]
        with self.assertRaises(ValueError):
            lens_rules.check_rules(bad, {"level": "low", "findings": []}, ORD)

    def test_malformed_require_shape_raises(self):
        bad = [{"when": {"level": "low"}, "require": {"findings.types": ["praise"]}}]
        with self.assertRaises(ValueError):
            lens_rules.check_rules(bad, {"level": "low", "findings": [{"type": "capitulation"}]}, ORD)

if __name__ == "__main__":
    unittest.main()
