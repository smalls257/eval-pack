import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import lens_checks  # noqa: E402

CLAIMS = [{"id": "c1", "covers": ["fix-a", "fix-b"]}]

class TestCoverage(unittest.TestCase):
    def test_full_coverage_passes(self):
        self.assertEqual(lens_checks.claim_coverage(CLAIMS, {"fix-a", "fix-b"}), (True, []))

    def test_claim_covering_unknown_fixture_fails(self):
        passed, msgs = lens_checks.claim_coverage(CLAIMS, {"fix-a"})
        self.assertFalse(passed)
        self.assertTrue(any("fix-b" in m for m in msgs))

    def test_uncovered_fixture_fails(self):
        passed, msgs = lens_checks.claim_coverage(CLAIMS, {"fix-a", "fix-b", "orphan"})
        self.assertFalse(passed)
        self.assertTrue(any("orphan" in m for m in msgs))

    def test_claim_with_no_covers_fails(self):
        passed, msgs = lens_checks.claim_coverage([{"id": "c2", "covers": []}], set())
        self.assertFalse(passed)

if __name__ == "__main__":
    unittest.main()
