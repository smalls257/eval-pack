import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import render_html  # noqa: E402


def _pack(d, *, transcript=None, metrics=None):
    p = Path(d)
    if transcript is not None:
        (p / "transcript.jsonl").write_text(
            "\n".join(json.dumps(e) for e in transcript) + ("\n" if transcript else ""),
            encoding="utf-8")
    if metrics is not None:
        (p / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
    return p


_GOOD_TURNS = [
    {"type": "user", "message": {"content": "hi"}},
    {"type": "assistant", "message": {"content": [{"type": "text", "text": "ok"}]}},
]


class ValidatePackTests(unittest.TestCase):
    def test_complete_pack_has_no_gaps(self):
        with tempfile.TemporaryDirectory() as d:
            _pack(d, transcript=_GOOD_TURNS, metrics={"turnCount": 2})
            self.assertEqual(render_html.validate_pack(Path(d)), [])

    def test_missing_transcript_is_a_gap(self):
        with tempfile.TemporaryDirectory() as d:
            _pack(d, metrics={"turnCount": 2})
            gaps = render_html.validate_pack(Path(d))
            self.assertTrue(any("transcript" in g for g in gaps))

    def test_empty_transcript_is_a_gap(self):
        with tempfile.TemporaryDirectory() as d:
            _pack(d, transcript=[], metrics={"turnCount": 2})
            self.assertTrue(any("transcript" in g for g in render_html.validate_pack(Path(d))))

    def test_transcript_without_turns_is_a_gap(self):
        with tempfile.TemporaryDirectory() as d:
            _pack(d, transcript=[{"type": "permission-mode"}, {"type": "summary"}],
                  metrics={"turnCount": 2})
            self.assertTrue(any("no conversation turns" in g
                                for g in render_html.validate_pack(Path(d))))

    def test_missing_or_empty_metrics_is_a_gap(self):
        with tempfile.TemporaryDirectory() as d:
            _pack(d, transcript=_GOOD_TURNS, metrics={})  # backfilled empty
            self.assertTrue(any("metrics" in g for g in render_html.validate_pack(Path(d))))



class WriteZipTranscriptTests(unittest.TestCase):
    def _pack(self, d):
        p = Path(d) / "pk"; p.mkdir()
        (p / "index.html").write_text("x", encoding="utf-8")
        (p / "transcript.jsonl").write_text('{"uuid":"u1"}\n', encoding="utf-8")
        return p

    def _names(self, zpath):
        import zipfile
        return zipfile.ZipFile(zpath).namelist()

    def test_includes_transcript_when_true(self):
        with tempfile.TemporaryDirectory() as d:
            z = Path(d) / "o.zip"
            render_html.write_zip(self._pack(d), z, "sid", True)
            self.assertTrue(any(n.endswith("transcript.jsonl") for n in self._names(z)))

    def test_excludes_transcript_when_false(self):
        with tempfile.TemporaryDirectory() as d:
            z = Path(d) / "o.zip"
            render_html.write_zip(self._pack(d), z, "sid", False)
            names = self._names(z)
            self.assertFalse(any(n.endswith("transcript.jsonl") for n in names))
            self.assertTrue(any(n.endswith("index.html") for n in names))

    def test_env_bool_defaults_and_override(self):
        import os
        os.environ.pop("CLAUDE_PLUGIN_OPTION_includeRawTranscript", None)
        self.assertFalse(render_html._env_bool("includeRawTranscript", False))
        self.assertTrue(render_html._env_bool("includeRenderedTranscript", True))
        os.environ["CLAUDE_PLUGIN_OPTION_includeRawTranscript"] = "true"
        self.assertTrue(render_html._env_bool("includeRawTranscript", False))
        os.environ.pop("CLAUDE_PLUGIN_OPTION_includeRawTranscript", None)

    def test_write_zip_transcript_gating(self):
        import zipfile, tempfile, pathlib
        with tempfile.TemporaryDirectory() as d:
            pack = pathlib.Path(d) / "pack"; pack.mkdir()
            (pack / "transcript.jsonl").write_text("{}\n")
            (pack / "transcript.html").write_text("<html>convo</html>")
            (pack / "index.html").write_text("<html></html>")
            def names(raw, rendered):
                zp = pathlib.Path(d) / f"o-{raw}-{rendered}.zip"
                render_html.write_zip(pack, zp, "sid", raw, rendered)
                with zipfile.ZipFile(zp) as z: return set(n.split("/",1)[1] for n in z.namelist())
            default = names(False, True)
            self.assertIn("transcript.html", default)
            self.assertNotIn("transcript.jsonl", default)
            self.assertIn("transcript.jsonl", names(True, True))
            self.assertNotIn("transcript.html", names(False, False))


class StandaloneConfigFallbackTests(unittest.TestCase):
    """Standalone render (no eval-config.json) must honor the legacy env vars.

    read_config(None) ignores env by design (fresh DEFAULTS), so without the
    fallback a user-requested transcript exclusion would be silently dropped —
    a privacy-adjacent Silent Fallback. Raw and rendered are gated independently.
    """

    _KEYS = ("CLAUDE_PLUGIN_OPTION_includeRawTranscript",
             "CLAUDE_PLUGIN_OPTION_includeRenderedTranscript")

    def _with_env(self, values, fn):
        import os
        old = {k: os.environ.get(k) for k in self._KEYS}
        for k in self._KEYS:
            v = values.get(k)
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        try:
            return fn()
        finally:
            for k in self._KEYS:
                if old[k] is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = old[k]

    def test_standalone_defaults_raw_off_rendered_on(self):
        with tempfile.TemporaryDirectory() as d:
            missing = Path(d) / "eval-config.json"  # main()'s no-config branch
            cfg = self._with_env({}, lambda: render_html._resolve_render_config(missing))
            self.assertIs(cfg["includeRawTranscript"], False)
            self.assertIs(cfg["includeRenderedTranscript"], True)

    def test_standalone_raw_env_overrides_independently(self):
        with tempfile.TemporaryDirectory() as d:
            missing = Path(d) / "eval-config.json"
            cfg = self._with_env(
                {"CLAUDE_PLUGIN_OPTION_includeRawTranscript": "true"},
                lambda: render_html._resolve_render_config(missing))
            self.assertIs(cfg["includeRawTranscript"], True)
            self.assertIs(cfg["includeRenderedTranscript"], True)  # unchanged

    def test_standalone_rendered_env_overrides_independently(self):
        with tempfile.TemporaryDirectory() as d:
            missing = Path(d) / "eval-config.json"
            cfg = self._with_env(
                {"CLAUDE_PLUGIN_OPTION_includeRenderedTranscript": "off"},
                lambda: render_html._resolve_render_config(missing))
            self.assertIs(cfg["includeRenderedTranscript"], False)
            self.assertIs(cfg["includeRawTranscript"], False)  # unchanged

    def test_standalone_env_garbage_raises(self):
        # Garbage must fail loud (ConfigError), never silently bundle.
        import config as _config
        with tempfile.TemporaryDirectory() as d:
            missing = Path(d) / "eval-config.json"
            with self.assertRaises(_config.ConfigError):
                self._with_env(
                    {"CLAUDE_PLUGIN_OPTION_includeRawTranscript": "maybe"},
                    lambda: render_html._resolve_render_config(missing))

    def test_resolved_config_file_wins_over_env(self):
        # Pipeline path: env was already layered at resolve time — the resolved
        # file is authoritative, so render must NOT re-apply the raw env var.
        with tempfile.TemporaryDirectory() as d:
            cfg_path = Path(d) / "eval-config.json"
            resolved = render_html.read_config(None)
            resolved["includeRawTranscript"] = False
            cfg_path.write_text(json.dumps(resolved), encoding="utf-8")
            cfg = self._with_env(
                {"CLAUDE_PLUGIN_OPTION_includeRawTranscript": "true"},
                lambda: render_html._resolve_render_config(cfg_path))
            self.assertIs(cfg["includeRawTranscript"], False)


if __name__ == "__main__":
    unittest.main()
