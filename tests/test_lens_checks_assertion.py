# tests/test_lens_checks_assertion.py
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import lens_checks  # noqa: E402

ORD = ["low", "medium", "high"]

class TestAssertion(unittest.TestCase):
    def test_score_band(self):
        self.assertTrue(lens_checks.assert_one({"score": 88}, {"score": {"min": 70, "max": 100}}, ORD))
        self.assertFalse(lens_checks.assert_one({"score": 40}, {"score": {"min": 70, "max": 100}}, ORD))

    def test_level_min(self):
        self.assertTrue(lens_checks.assert_one({"level": "high"}, {"level": {"min": "medium"}}, ORD))
        self.assertFalse(lens_checks.assert_one({"level": "low"}, {"level": {"min": "medium"}}, ORD))

    def test_findings_include_exclude(self):
        out = {"findings": [{"type": "capitulation"}]}
        self.assertTrue(lens_checks.assert_one(out, {"findings": {"include": ["capitulation"], "exclude": ["praise"]}}, ORD))
        self.assertFalse(lens_checks.assert_one(out, {"findings": {"include": ["drift"]}}, ORD))

    def test_non_evidential_finding_does_not_satisfy_include_or_trip_exclude(self):
        out = {"findings": [{"type": "capitulation", "evidential": False}]}
        self.assertFalse(lens_checks.assert_one(out, {"findings": {"include": ["capitulation"]}}, ORD))
        self.assertTrue(lens_checks.assert_one(out, {"findings": {"exclude": ["capitulation"]}}, ORD))

    def test_majority_passes(self):
        trials = [{"score": 88}, {"score": 91}, {"score": 40}]
        self.assertEqual(lens_checks.output_assertion(trials, {"score": {"min": 70, "max": 100}}, ORD),
                         {"passed": True, "meeting": 2, "n": 3})

    def test_minority_fails(self):
        trials = [{"score": 88}, {"score": 40}, {"score": 30}]
        self.assertFalse(lens_checks.output_assertion(trials, {"score": {"min": 70, "max": 100}}, ORD)["passed"])

if __name__ == "__main__":
    unittest.main()
