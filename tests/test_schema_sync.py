# tests/test_schema_sync.py
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import config  # noqa: E402


class TestSchemaSync(unittest.TestCase):
    def test_schema_keys_match_defaults(self):
        schema = json.loads((ROOT / "schema" / "eval-pack.schema.json").read_text())
        schema_keys = set(schema["properties"]) - {"extends", "$schema"}
        self.assertEqual(
            schema_keys, set(config.DEFAULTS),
            "schema properties and DEFAULTS must stay in sync",
        )

    def test_additional_properties_false(self):
        schema = json.loads((ROOT / "schema" / "eval-pack.schema.json").read_text())
        self.assertFalse(schema["additionalProperties"])


if __name__ == "__main__":
    unittest.main()
