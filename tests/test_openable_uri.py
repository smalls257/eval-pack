import sys
import warnings
from pathlib import Path, PureWindowsPath
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import render_html  # noqa: E402


class OpenableReportUriTests(unittest.TestCase):
    """Field bug: the printed 'Open:' link was a hand-built f'file://{path}' that broke
    on Windows (backslashes + bare drive letter) and truncated on any path with a space,
    so users couldn't open the report that landed in AppData\\Local\\Temp. The URI must be
    a proper, platform-correct, percent-encoded file:// URI."""

    def test_posix_path_with_space_is_percent_encoded(self):
        uri = render_html.openable_report_uri(Path("/var/folders/xx/T/eval pack abc"))
        self.assertEqual(uri, "file:///var/folders/xx/T/eval%20pack%20abc/index.html")
        self.assertNotIn(" ", uri)  # a literal space truncates the link in terminals

    def test_uri_is_absolute_file_scheme(self):
        uri = render_html.openable_report_uri(Path("/tmp/eval-pack-abc"))
        self.assertTrue(uri.startswith("file:///"))
        self.assertTrue(uri.endswith("/index.html"))

    def test_windows_path_yields_triple_slash_drive_form(self):
        # PureWindowsPath.as_uri() models what native-Windows Path.as_uri() emits (the
        # production call is concrete Path.as_uri(), not deprecated): file:///C:/... with
        # forward slashes — never the broken file://C:\... form the field bug produced.
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
