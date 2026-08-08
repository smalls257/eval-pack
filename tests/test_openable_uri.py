import sys
import tempfile
import warnings
from pathlib import Path, PureWindowsPath
from urllib.parse import urlparse
from urllib.request import url2pathname
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import render_html  # noqa: E402


class VerifyOpenableUriTests(unittest.TestCase):
    """Field bug: the printed 'Open:' link was a hand-built f'file://{path}' that broke
    on Windows (backslashes + bare drive letter) and truncated on any path with a space,
    so users couldn't open the report that landed in AppData\\Local\\Temp. The URI must be
    a proper, platform-correct, percent-encoded file:// URI.

    verify_openable now owns this rule (the dead openable_report_uri helper was removed to
    kill the two-owners-of-one-URI-rule drift risk). Because verify_openable only returns a
    URI for an index.html that ACTUALLY EXISTS, these tests build a real file so the
    percent-encoding round-trip is genuinely exercised, not modelled."""

    def _open_dir_with(self, tmp, subpath):
        open_dir = Path(tmp) / subpath
        open_dir.mkdir(parents=True)
        (open_dir / "index.html").write_text("<html></html>", encoding="utf-8")
        return open_dir

    def test_posix_path_with_space_is_percent_encoded(self):
        with tempfile.TemporaryDirectory() as tmp:
            open_dir = self._open_dir_with(tmp, "eval pack abc")
            uri = render_html.verify_openable(open_dir)
            self.assertIsNotNone(uri)
            self.assertIn("eval%20pack%20abc", uri)  # the space is percent-encoded
            self.assertNotIn(" ", uri)  # a literal space truncates the link in terminals
            # The percent-encoded URI round-trips back to the real file it names.
            decoded = Path(url2pathname(urlparse(uri).path))
            self.assertTrue(decoded.is_file())

    def test_uri_is_absolute_file_scheme_ending_in_index_html(self):
        with tempfile.TemporaryDirectory() as tmp:
            open_dir = self._open_dir_with(tmp, "eval-pack-abc")
            uri = render_html.verify_openable(open_dir)
            self.assertIsNotNone(uri)
            self.assertTrue(uri.startswith("file:///"))
            self.assertTrue(uri.endswith("/index.html"))

    def test_windows_path_yields_triple_slash_drive_form(self):
        # verify_openable requires a real on-disk index.html, so it can't model a pure
        # Windows path on this mac. Assert the URI SHAPE the production Path.as_uri() emits
        # for a Windows path directly: file:///C:/... with forward slashes — never the
        # broken file://C:\... form the field bug produced.
        win = PureWindowsPath(r"C:\Users\jason\AppData\Local\Temp\eval-pack-abc") / "index.html"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)  # PurePath.as_uri (mac-side model only)
            uri = win.as_uri()
        self.assertEqual(
            uri, "file:///C:/Users/jason/AppData/Local/Temp/eval-pack-abc/index.html")
        self.assertNotIn("\\", uri)
        self.assertFalse(uri.startswith("file://C:"))  # the broken shape the bug produced


if __name__ == "__main__":
    unittest.main()
