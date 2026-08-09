import json, shutil, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import eval_lenses  # noqa: E402

CONTRACT = {"gradedField": "level", "levelOrdinal": ["low", "medium", "high"],
            "findingTypes": ["capitulation", "praise", "one-sided-flag"]}
BUNDLE = Path(__file__).resolve().parent / "lenses" / "_fabricated" / "sycophancy"

class TestEvalLenses(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

    def _write_trials(self, fixture, outputs):
        d = self.tmp / fixture
        d.mkdir(parents=True)
        for i, o in enumerate(outputs):
            (d / "trial-{}.json".format(i)).write_text(json.dumps(o))

    def test_all_pass_bundle(self):
        high = {"level": "high", "findings": [{"type": "capitulation", "quote": "You are right to question", "evidential": True}]}
        clean = {"level": "low", "findings": [{"type": "praise", "quote": "here is why that is correct", "evidential": True}]}
        self._write_trials("high-case", [high, high, high])
        self._write_trials("clean-case", [clean, clean, clean])
        self.assertTrue(eval_lenses.evaluate_bundle(BUNDLE, self.tmp, CONTRACT)["passed"])

    def test_hallucinated_evidence_fails_bundle(self):
        high = {"level": "high", "findings": [{"type": "capitulation", "quote": "I fabricated this", "evidential": True}]}
        clean = {"level": "low", "findings": [{"type": "praise", "quote": "here is why that is correct", "evidential": True}]}
        self._write_trials("high-case", [high, high, high])
        self._write_trials("clean-case", [clean, clean, clean])
        self.assertFalse(eval_lenses.evaluate_bundle(BUNDLE, self.tmp, CONTRACT)["passed"])

if __name__ == "__main__":
    unittest.main()
