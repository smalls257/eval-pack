# tests/test_real_bundles_e2e.py
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import eval_lenses  # noqa: E402

LENSES = Path(__file__).resolve().parent / "lenses"
DRIFT_C = {"gradedField": "score", "findingTypes": ["unmet", "unrequested", "met"]}
SYCO_C = {"gradedField": "level", "levelOrdinal": ["low", "medium", "high"],
          "findingTypes": ["capitulation", "false-belief", "compound", "drift", "praise", "one-sided-flag"]}

class TestRealBundlesE2E(unittest.TestCase):
    def test_drift_bundle_passes_on_recorded_trials(self):
        bundle = LENSES / "requirement-drift"
        report = eval_lenses.evaluate_bundle(bundle, bundle / "trials", DRIFT_C)
        self.assertTrue(report["passed"], report)

    def test_syco_bundle_passes_on_recorded_trials(self):
        bundle = LENSES / "sycophancy"
        report = eval_lenses.evaluate_bundle(bundle, bundle / "trials", SYCO_C)
        self.assertTrue(report["passed"], report)

if __name__ == "__main__":
    unittest.main()
