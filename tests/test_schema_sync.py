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

    def test_display_enum_matches_config_display_modes(self):
        schema = json.loads((ROOT / "schema" / "eval-pack.schema.json").read_text())
        enum = schema["properties"]["analysisLenses"]["items"]["properties"]["display"]["enum"]
        self.assertEqual(list(enum), list(config.DISPLAY_MODES))

    def test_schema_types_and_defaults_match(self):
        # Guard against type/default drift, not just key drift: the schema must
        # agree with the runtime _TYPES and DEFAULTS for every known key.
        schema = json.loads((ROOT / "schema" / "eval-pack.schema.json").read_text())
        props = schema["properties"]
        json_to_py = {"integer": int, "array": list, "string": str, "boolean": bool, "object": dict}
        for key, typ in config._TYPES.items():
            with self.subTest(key=key):
                self.assertEqual(json_to_py[props[key]["type"]], typ)
                self.assertEqual(props[key]["default"], config.DEFAULTS[key])


if __name__ == "__main__":
    unittest.main()
