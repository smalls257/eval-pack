import json
import sys
import tempfile
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import render_html  # noqa: E402


class ReadPluginVersionTests(unittest.TestCase):
    """The report footer stamps the eval-pack version that produced it, read from the
    plugin manifest. A missing/broken manifest must yield '' (informational stamp — never
    fail the render)."""

    def _root_with_manifest(self, tmp, obj):
        root = Path(tmp)
        (root / ".claude-plugin").mkdir()
        (root / ".claude-plugin" / "plugin.json").write_text(json.dumps(obj), encoding="utf-8")
        return root

    def test_reads_version_from_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._root_with_manifest(tmp, {"name": "eval-pack", "version": "0.4.0-rc.8"})
            self.assertEqual(render_html.read_plugin_version(root), "0.4.0-rc.8")

    def test_missing_manifest_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(render_html.read_plugin_version(Path(tmp)), "")

    def test_malformed_manifest_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".claude-plugin").mkdir()
            (root / ".claude-plugin" / "plugin.json").write_text("{not json", encoding="utf-8")
            self.assertEqual(render_html.read_plugin_version(root), "")

    def test_version_absent_from_manifest_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._root_with_manifest(tmp, {"name": "eval-pack"})
            self.assertEqual(render_html.read_plugin_version(root), "")


if __name__ == "__main__":
    unittest.main()
