import json
import sys
import tempfile
import zipfile
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import render_html  # noqa: E402


class LoadPriorRoundsTests(unittest.TestCase):
    def _zip_with_data(self, zip_path, session_id, rounds):
        data = {"sessionId": session_id, "rounds": rounds}
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr(f"{session_id}/data.json", json.dumps(data))

    def test_carries_rounds_even_when_session_id_differs(self):
        with tempfile.TemporaryDirectory() as d:
            zp = Path(d) / "branch.zip"
            self._zip_with_data(zp, "OLD-SESSION", [{"screenshots": []}])
            prev_data, names = render_html.load_prior_rounds(zp)
            self.assertEqual(len(prev_data.get("rounds", [])), 1)

    def test_missing_zip_returns_empty(self):
        with tempfile.TemporaryDirectory() as d:
            prev_data, names = render_html.load_prior_rounds(Path(d) / "none.zip")
            self.assertEqual(prev_data, {})
            self.assertEqual(names, set())


if __name__ == "__main__":
    unittest.main()
