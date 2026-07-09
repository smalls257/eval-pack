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

    def test_include_transcript_env(self):
        import os
        os.environ.pop("CLAUDE_PLUGIN_OPTION_includeTranscript", None)
        self.assertTrue(render_html._include_transcript())       # default true
        os.environ["CLAUDE_PLUGIN_OPTION_includeTranscript"] = "false"
        self.assertFalse(render_html._include_transcript())
        os.environ.pop("CLAUDE_PLUGIN_OPTION_includeTranscript", None)


class StandaloneConfigFallbackTests(unittest.TestCase):
    """Standalone render (no eval-config.json) must honor the legacy env var.

    read_config(None) ignores env by design (fresh DEFAULTS), so without the
    fallback a user-requested transcript exclusion would be silently dropped —
    a privacy-adjacent Silent Fallback.
    """

    def _with_env(self, value, fn):
        import os
        old = os.environ.get("CLAUDE_PLUGIN_OPTION_includeTranscript")
        if value is None:
            os.environ.pop("CLAUDE_PLUGIN_OPTION_includeTranscript", None)
        else:
            os.environ["CLAUDE_PLUGIN_OPTION_includeTranscript"] = value
        try:
            return fn()
        finally:
            if old is None:
                os.environ.pop("CLAUDE_PLUGIN_OPTION_includeTranscript", None)
            else:
                os.environ["CLAUDE_PLUGIN_OPTION_includeTranscript"] = old

    def test_standalone_cfg_falls_back_to_env(self):
        with tempfile.TemporaryDirectory() as d:
            missing = Path(d) / "eval-config.json"  # main()'s no-config branch
            def resolve():
                # read_config(None) ignores env (by design) …
                self.assertIs(render_html.read_config(None)["includeTranscript"], True)
                # … but render-time resolution must honor the legacy env var.
                return render_html._resolve_render_config(missing)
            cfg = self._with_env("false", resolve)
            self.assertIs(cfg["includeTranscript"], False)

    def test_standalone_defaults_true_without_env(self):
        with tempfile.TemporaryDirectory() as d:
            missing = Path(d) / "eval-config.json"
            cfg = self._with_env(None, lambda: render_html._resolve_render_config(missing))
            self.assertIs(cfg["includeTranscript"], True)

    def test_standalone_env_off_excludes_transcript(self):
        # "off" is False in the pipeline's canonical coercer — the standalone
        # path must agree, or the transcript is silently bundled.
        with tempfile.TemporaryDirectory() as d:
            missing = Path(d) / "eval-config.json"
            cfg = self._with_env("off", lambda: render_html._resolve_render_config(missing))
            self.assertIs(cfg["includeTranscript"], False)

    def test_standalone_env_garbage_raises(self):
        # Garbage must fail loud (ConfigError), never silently bundle.
        import config as _config
        with tempfile.TemporaryDirectory() as d:
            missing = Path(d) / "eval-config.json"
            with self.assertRaises(_config.ConfigError):
                self._with_env("maybe", lambda: render_html._resolve_render_config(missing))

    def test_resolved_config_file_wins_over_env(self):
        # Pipeline path: env was already layered at resolve time — the resolved
        # file is authoritative, so render must NOT re-apply the raw env var.
        with tempfile.TemporaryDirectory() as d:
            cfg_path = Path(d) / "eval-config.json"
            resolved = render_html.read_config(None)
            resolved["includeTranscript"] = True
            cfg_path.write_text(json.dumps(resolved), encoding="utf-8")
            cfg = self._with_env("false", lambda: render_html._resolve_render_config(cfg_path))
            self.assertIs(cfg["includeTranscript"], True)


if __name__ == "__main__":
    unittest.main()
