import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import lens_manifest  # noqa: E402

MD = '# Title\n\nprose\n\n```json\n{"gradedField": "score", "findingTypes": ["met"]}\n```\n\nmore\n'

class TestLensManifest(unittest.TestCase):
    def test_extract_first_json_block(self):
        self.assertEqual(lens_manifest.extract_json_block(MD),
                         {"gradedField": "score", "findingTypes": ["met"]})

    def test_extract_missing_block_raises(self):
        with self.assertRaises(ValueError):
            lens_manifest.extract_json_block("no fenced blocks here")

    def test_extract_invalid_json_raises(self):
        with self.assertRaises(ValueError):
            lens_manifest.extract_json_block("```json\n{not valid}\n```")

    def test_parse_output_contract(self):
        self.assertEqual(lens_manifest.parse_output_contract(MD)["gradedField"], "score")

    def test_parse_basis_uses_first_block(self):
        md = '```json\n{"sources": [], "claims": [], "rules": []}\n```'
        self.assertEqual(lens_manifest.parse_basis(md), {"sources": [], "claims": [], "rules": []})

if __name__ == "__main__":
    unittest.main()
