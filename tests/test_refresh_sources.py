import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import refresh_sources  # noqa: E402

class TestRefreshSources(unittest.TestCase):
    def test_build_ledger_uses_resolver(self):
        sources = [{"id": "s1", "citation": "arXiv:1", "title": "Declared Title"}]
        def fake_resolve(citation):
            return {"title": "Resolved Title", "authors": "A. Uthor", "date": "2026"}
        ledger = refresh_sources.build_ledger(sources, fake_resolve)
        self.assertEqual(ledger["s1"]["title"], "Resolved Title")
        self.assertEqual(ledger["s1"]["authors"], "A. Uthor")
        self.assertIn("resolved_at", ledger["s1"])

if __name__ == "__main__":
    unittest.main()
