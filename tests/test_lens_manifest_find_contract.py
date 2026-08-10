import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import lens_manifest  # noqa: E402

CONTRACT_FIRST = '```json\n{"gradedField": "score", "findingTypes": ["met"]}\n```\n\n```json\n{"skill": "x", "findings": []}\n```'
EXAMPLE_FIRST = '```json\n{"skill": "x", "score": 1, "findings": []}\n```\n\n```json\n{"gradedField": "level", "levelOrdinal": ["low","high"]}\n```'

class TestFindContract(unittest.TestCase):
    def test_finds_contract_when_first(self):
        self.assertEqual(lens_manifest.find_output_contract(CONTRACT_FIRST)["gradedField"], "score")

    def test_finds_contract_after_an_example_block(self):
        # the example block (no gradedField) must be skipped; the contract is found regardless of order
        self.assertEqual(lens_manifest.find_output_contract(EXAMPLE_FIRST)["gradedField"], "level")

    def test_returns_none_when_no_contract(self):
        self.assertIsNone(lens_manifest.find_output_contract('```json\n{"skill": "x"}\n```'))

    def test_skips_malformed_block(self):
        md = '```json\n{not valid}\n```\n\n```json\n{"gradedField": "none"}\n```'
        self.assertEqual(lens_manifest.find_output_contract(md)["gradedField"], "none")

if __name__ == "__main__":
    unittest.main()
