# tests/test_report_config.py
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import render_html  # noqa: E402
import config  # noqa: E402


class TestReportConfig(unittest.TestCase):
    # Keys the report template (scripts.js) reads off data.evalConfig. If render_html omits
    # one, the knob validates + resolves but silently does nothing — a dead knob.
    TEMPLATE_KEYS = {
        "brandName", "reportTitle", "footerText", "subjectNoun", "defaultTheme", "messages",
        "repoBaseUrl", "sections",
    }

    def test_surfaces_all_template_consumed_keys(self):
        surfaced = set(render_html.report_config(config.DEFAULTS))
        missing = self.TEMPLATE_KEYS - surfaced
        self.assertEqual(missing, set(), "dead knobs (template reads, render omits): %s" % missing)

    def test_all_surfaced_keys_are_real_config(self):
        for k in render_html.report_config(config.DEFAULTS):
            self.assertIn(k, config.DEFAULTS)


if __name__ == "__main__":
    unittest.main()
