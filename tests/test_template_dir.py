# tests/test_template_dir.py
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import render_html  # noqa: E402

BUNDLED = SCRIPTS.parent / "templates" / "html"


class TestTemplateOverride(unittest.TestCase):
    def test_user_file_wins_bundled_fills_gaps(self):
        with tempfile.TemporaryDirectory() as d:
            user_dir = Path(d) / "mytpl"
            user_dir.mkdir()
            (user_dir / "styles.css").write_text("/* CUSTOM */", encoding="utf-8")
            pack = Path(d) / "pack"
            render_html.build_directory_structure(pack, BUNDLED, user_dir)
            self.assertEqual((pack / "styles.css").read_text(encoding="utf-8"), "/* CUSTOM */")
            self.assertIn("<html", (pack / "index.html").read_text(encoding="utf-8"))  # bundled fallback

    def test_no_override_uses_bundled(self):
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d) / "pack"
            render_html.build_directory_structure(pack, BUNDLED, None)
            self.assertIn("<html", (pack / "index.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
