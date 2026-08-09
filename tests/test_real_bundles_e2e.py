# tests/test_real_bundles_e2e.py
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import eval_lenses  # noqa: E402
from lens_manifest import parse_output_contract  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
LENSES = Path(__file__).resolve().parent / "lenses"


def _shipped_contract(skill):
    """The gate must exercise the SAME contract the lens ships (agents/lenses/<skill>.md),
    never a hand-copied subset — a looser gate is a Paper Tiger that green-lights fixtures
    whose recorded trials would fail the checks the lens actually enforces (evidenceRoles,
    requiresGuidance)."""
    md = (REPO / "agents" / "lenses" / "{}.md".format(skill)).read_text(encoding="utf-8")
    return parse_output_contract(md)


class TestRealBundlesE2E(unittest.TestCase):
    def test_drift_bundle_passes_on_recorded_trials(self):
        bundle = LENSES / "requirement-drift"
        report = eval_lenses.evaluate_bundle(bundle, bundle / "trials",
                                             _shipped_contract("requirement-drift"))
        self.assertTrue(report["passed"], report)

    def test_syco_bundle_passes_on_recorded_trials(self):
        bundle = LENSES / "sycophancy"
        report = eval_lenses.evaluate_bundle(bundle, bundle / "trials",
                                             _shipped_contract("sycophancy"))
        self.assertTrue(report["passed"], report)

    def test_user_improvements_bundle_passes_on_recorded_trials(self):
        bundle = LENSES / "user-improvements"
        report = eval_lenses.evaluate_bundle(bundle, bundle / "trials",
                                             _shipped_contract("user-improvements"))
        self.assertTrue(report["passed"], report)


if __name__ == "__main__":
    unittest.main()
