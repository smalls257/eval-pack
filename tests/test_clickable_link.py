import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import render_html  # noqa: E402


class ClickableLinkTests(unittest.TestCase):
    """The 'Open:' line prints a bare file:// URI; neither Claude Code nor most terminals
    auto-linkify file://, so it renders as dead text. We emit an OSC 8 hyperlink so the URL
    is clickable (Claude Code honours OSC 8 in tool output). We do NOT gate on isatty —
    Claude Code pipes tool stdout, so isatty would suppress the link in the path that
    matters — but we honour NO_COLOR / TERM=dumb so logs/CI can get the plain URL."""

    URI = "file:///private/var/tmp/eval-pack-abc/index.html"

    def test_default_emits_osc8_hyperlink(self):
        # a normal terminal env (no NO_COLOR, real TERM) => clickable
        out = render_html.clickable_link(self.URI, env={"TERM": "xterm-256color"})
        self.assertTrue(out.startswith("\033]8;;" + self.URI + "\033\\"))
        self.assertTrue(out.endswith("\033]8;;\033\\"))
        self.assertEqual(out.count(self.URI), 2)  # OSC 8 target + visible label

    def test_emits_even_when_not_a_tty(self):
        # the regression that mattered: CC pipes stdout (not a TTY); the link must still emit.
        # (env, not isatty, is the gate — a normal TERM with no NO_COLOR emits regardless.)
        out = render_html.clickable_link(self.URI, env={"TERM": "xterm"})
        self.assertIn("\033]8;;", out)

    def test_no_color_is_plain_uri(self):
        out = render_html.clickable_link(self.URI, env={"NO_COLOR": "1", "TERM": "xterm"})
        self.assertEqual(out, self.URI)
        self.assertNotIn("\033", out)

    def test_dumb_or_empty_term_is_plain(self):
        for term in ("dumb", ""):
            out = render_html.clickable_link(self.URI, env={"TERM": term})
            self.assertEqual(out, self.URI, term)

    def test_custom_label_shows_but_target_is_uri(self):
        out = render_html.clickable_link(self.URI, label="Open report", env={"TERM": "xterm"})
        self.assertIn("\033]8;;" + self.URI + "\033\\Open report\033]8;;\033\\", out)


if __name__ == "__main__":
    unittest.main()
