import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import render_html  # noqa: E402


class TestBuildArtifactInventory(unittest.TestCase):
    def test_empty_pack_yields_no_artifacts(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(render_html.build_artifact_inventory(Path(d)), [])

    def test_transcript_screenshot_and_log_are_listed(self):
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d)
            (pack / "transcript.html").write_text("<html></html>", encoding="utf-8")
            (pack / "screenshots").mkdir()
            (pack / "screenshots" / "step1.png").write_bytes(b"\x89PNG")
            (pack / "logs").mkdir()
            (pack / "logs" / "build.log").write_text("ok", encoding="utf-8")

            items = render_html.build_artifact_inventory(pack)

            by_path = {i["path"]: i for i in items}
            self.assertEqual(by_path["transcript.html"], {
                "name": "Transcript", "path": "transcript.html", "type": "transcript",
                "description": "Rendered conversation — commands, outputs, failures",
            })
            self.assertEqual(by_path["screenshots/step1.png"]["type"], "screenshot")
            self.assertEqual(by_path["screenshots/step1.png"]["name"], "step1.png")
            self.assertEqual(by_path["logs/build.log"]["type"], "log")
            self.assertEqual(by_path["logs/build.log"]["name"], "build.log")

    def test_missing_files_are_not_listed(self):
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d)
            (pack / "screenshots").mkdir()  # empty dir, no pngs
            items = render_html.build_artifact_inventory(pack)
            self.assertEqual(items, [])

    def test_known_data_files_map_to_data_type(self):
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d)
            (pack / "test-results.json").write_text("{}", encoding="utf-8")
            (pack / "metrics.json").write_text("{}", encoding="utf-8")
            (pack / "patterns.json").write_text("{}", encoding="utf-8")
            (pack / "tools.json").write_text("{}", encoding="utf-8")
            (pack / "lenses.json").write_text("{}", encoding="utf-8")

            items = render_html.build_artifact_inventory(pack)
            by_path = {i["path"]: i for i in items}

            self.assertEqual(by_path["test-results.json"]["type"], "tests")
            self.assertEqual(by_path["metrics.json"]["type"], "data")
            self.assertEqual(by_path["patterns.json"]["type"], "data")
            self.assertEqual(by_path["tools.json"]["type"], "data")
            self.assertEqual(by_path["lenses.json"]["type"], "data")

    def test_include_rendered_false_omits_transcript_entry(self):
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d)
            (pack / "transcript.html").write_text("<html></html>", encoding="utf-8")

            items = render_html.build_artifact_inventory(pack, include_rendered=False)

            self.assertEqual(items, [])

    def test_no_transcript_html_means_no_transcript_entry_even_if_included(self):
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d)
            items = render_html.build_artifact_inventory(pack, include_rendered=True)
            self.assertEqual(items, [])


if __name__ == "__main__":
    unittest.main()
