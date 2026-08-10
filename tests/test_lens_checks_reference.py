import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import lens_checks  # noqa: E402

SOURCES = [{"id": "chandra-2026", "citation": "arXiv:2602.19141",
            "title": "Sycophantic Chatbots Cause Delusional Spiraling"}]

class TestReference(unittest.TestCase):
    def test_matching_ledger_passes(self):
        ledger = {"chandra-2026": {"title": "Sycophantic Chatbots Cause Delusional Spiraling"}}
        self.assertEqual(lens_checks.reference_resolution(SOURCES, ledger), (True, []))

    def test_missing_ledger_entry_fails(self):
        passed, msgs = lens_checks.reference_resolution(SOURCES, {})
        self.assertFalse(passed)
        self.assertTrue(msgs)

    def test_title_mismatch_fails(self):
        ledger = {"chandra-2026": {"title": "A Completely Different Paper"}}
        passed, msgs = lens_checks.reference_resolution(SOURCES, ledger)
        self.assertFalse(passed)
        self.assertTrue(msgs)

if __name__ == "__main__":
    unittest.main()
