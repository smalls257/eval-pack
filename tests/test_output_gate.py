import sys
import zipfile
from pathlib import Path
import tempfile
import unittest
from urllib.parse import urlparse
from urllib.request import url2pathname

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import render_html  # noqa: E402


class VerifyZipIntegrityTests(unittest.TestCase):
    """Deterministic gate: the durable artifact (the zip) must reopen clean and
    contain the report's index.html, or the render must NOT report success.
    A corrupt/incomplete/missing-index zip is a real failure, not a warning."""

    def _make_pack_dir(self, tmp, with_index=True):
        pack_dir = Path(tmp) / "pack"
        pack_dir.mkdir()
        if with_index:
            (pack_dir / "index.html").write_text("<html>report</html>", encoding="utf-8")
        (pack_dir / "data.json").write_text("{}", encoding="utf-8")
        return pack_dir

    def test_returns_none_for_good_zip_with_index_html(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack_dir = self._make_pack_dir(tmp, with_index=True)
            zip_path = Path(tmp) / "out.zip"
            render_html.write_zip(pack_dir, zip_path, "sess123")
            result = render_html.verify_zip_integrity(zip_path, "sess123")
            self.assertIsNone(result)

    def test_returns_error_when_index_html_absent_from_pack(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack_dir = self._make_pack_dir(tmp, with_index=False)
            zip_path = Path(tmp) / "out.zip"
            render_html.write_zip(pack_dir, zip_path, "sess123")
            result = render_html.verify_zip_integrity(zip_path, "sess123")
            self.assertIsNotNone(result)
            self.assertIn("sess123/index.html", result)

    def test_returns_error_for_truncated_corrupt_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack_dir = self._make_pack_dir(tmp, with_index=True)
            zip_path = Path(tmp) / "out.zip"
            render_html.write_zip(pack_dir, zip_path, "sess123")

            # Truncate the zip bytes to simulate a corrupt/incomplete write.
            original = zip_path.read_bytes()
            zip_path.write_bytes(original[: len(original) // 2])

            result = render_html.verify_zip_integrity(zip_path, "sess123")
            self.assertIsNotNone(result)
            self.assertTrue(
                "unreadable" in result or "corrupt" in result,
                f"expected 'unreadable' or 'corrupt' in message, got: {result!r}",
            )

    def test_returns_error_for_missing_zip_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "does-not-exist.zip"
            result = render_html.verify_zip_integrity(zip_path, "sess123")
            self.assertIsNotNone(result)


class VerifyOpenableTests(unittest.TestCase):
    """Deterministic gate: only advertise an openable report whose index.html
    actually exists AND whose file:// URI round-trips back to that real file —
    so we never print a link that doesn't open."""

    def test_returns_roundtripping_uri_when_index_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            open_dir = Path(tmp) / "eval-pack-sess123"
            open_dir.mkdir()
            (open_dir / "index.html").write_text("<html></html>", encoding="utf-8")

            uri = render_html.verify_openable(open_dir)

            self.assertIsNotNone(uri)
            self.assertTrue(uri.startswith("file://"))
            decoded = Path(url2pathname(urlparse(uri).path))
            self.assertTrue(decoded.is_file())
            self.assertEqual(decoded.resolve(), (open_dir / "index.html").resolve())

    def test_returns_none_when_index_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            open_dir = Path(tmp) / "eval-pack-sess123"
            open_dir.mkdir()
            uri = render_html.verify_openable(open_dir)
            self.assertIsNone(uri)

    def test_returns_none_when_dir_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            open_dir = Path(tmp) / "does-not-exist"
            uri = render_html.verify_openable(open_dir)
            self.assertIsNone(uri)


class VerifyOpenableSpacePathTests(unittest.TestCase):
    """Integration-ish: guards that the rc.6 URI fix stays wired to the gate —
    a directory with a space in its name must still round-trip cleanly."""

    def test_open_dir_with_space_in_path_roundtrips(self):
        with tempfile.TemporaryDirectory() as tmp:
            open_dir = Path(tmp) / "eval pack containing space" / "eval-pack-sess123"
            open_dir.mkdir(parents=True)
            (open_dir / "index.html").write_text("<html></html>", encoding="utf-8")

            uri = render_html.verify_openable(open_dir)

            self.assertIsNotNone(uri)
            self.assertNotIn(" ", uri)
            decoded = Path(url2pathname(urlparse(uri).path))
            self.assertTrue(decoded.is_file())
            self.assertEqual(decoded.resolve(), (open_dir / "index.html").resolve())


if __name__ == "__main__":
    unittest.main()
