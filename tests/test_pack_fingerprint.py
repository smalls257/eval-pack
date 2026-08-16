import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import pack_fingerprint as pf

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "pack_fingerprint.py"


def test_lens_key_flips_on_each_axis():
    base = pf.lens_key(b"view-bytes", "1.0.0", "sonnet", "HEAD~1")
    assert pf.lens_key(b"view-bytes-CHANGED", "1.0.0", "sonnet", "HEAD~1") != base
    assert pf.lens_key(b"view-bytes", "1.0.1", "sonnet", "HEAD~1") != base
    assert pf.lens_key(b"view-bytes", "1.0.0", "opus", "HEAD~1") != base
    assert pf.lens_key(b"view-bytes", "1.0.0", "sonnet", "HEAD~2") != base
    assert pf.lens_key(b"view-bytes", "1.0.0", "sonnet", "HEAD~1") == base  # stable


def test_decide_reuse_matches_and_mismatches():
    prior = {"perLens": {"a": "K1", "b": "K2"}, "whole": "W"}
    cur   = {"perLens": {"a": "K1", "b": "K2-changed"}, "whole": "W2"}
    d = pf.decide_reuse(prior, cur)
    assert d["reuse"] == {"a"} and d["rerun"] == {"b"} and d["reuseAll"] is False


def test_missing_prior_reuses_nothing():
    cur = {"perLens": {"a": "K1"}, "whole": "W"}
    d = pf.decide_reuse(None, cur)      # fail-safe
    assert d["reuse"] == set() and d["rerun"] == {"a"} and d["reuseAll"] is False


def test_whole_match_reuses_all():
    prior = {"perLens": {"a": "K1"}, "whole": "W"}
    cur   = {"perLens": {"a": "K1"}, "whole": "W"}
    assert pf.decide_reuse(prior, cur)["reuseAll"] is True


def test_missing_whole_on_both_sides_is_not_reuseall():
    # Schema drift / non-fingerprint-shaped dicts: neither side has "whole", so
    # None == None must NOT be treated as a match. Falls through to the per-lens
    # path, which (since perLens also doesn't line up here) reuses nothing.
    prior = {"perLens": {"a": "K1"}}
    cur = {"perLens": {"a": "K1"}}
    d = pf.decide_reuse(prior, cur)
    assert d["reuseAll"] is False
    # per-lens path still finds a matching key even without "whole" present
    assert d["reuse"] == {"a"} and d["rerun"] == set()


def test_missing_whole_on_both_sides_with_no_matching_keys_reuses_nothing():
    prior = {"perLens": {"a": "K1"}}
    cur = {"perLens": {"b": "K2"}}
    d = pf.decide_reuse(prior, cur)
    assert d["reuseAll"] is False
    assert d["reuse"] == set() and d["rerun"] == {"b"}


def test_compute_reads_real_view_and_transcript_files(tmp_path, monkeypatch):
    monkeypatch.setattr(pf.lens_versions, "load_lock",
                         lambda: {"my-lens": {"version": "1.2.3"}, "full-lens": {"version": "9.9.9"}})

    pack_dir = tmp_path / "pack"
    (pack_dir / "views").mkdir(parents=True)
    (pack_dir / "views" / "conversation.jsonl").write_text('{"turn": 1}\n', encoding="utf-8")
    (pack_dir / "transcript.jsonl").write_text('{"turn": "full"}\n', encoding="utf-8")

    lenses = [
        {"skill": "my-lens", "model": "sonnet", "view": "conversation"},
        {"skill": "full-lens", "model": "sonnet", "view": "full"},
    ]
    out = pf.compute(str(pack_dir), lenses, "HEAD~1")
    key_before = out["perLens"]["my-lens"]
    full_key_before = out["perLens"]["full-lens"]

    # (a) changing the view file's bytes changes that lens's key
    (pack_dir / "views" / "conversation.jsonl").write_text('{"turn": 1, "changed": true}\n', encoding="utf-8")
    out2 = pf.compute(str(pack_dir), lenses, "HEAD~1")
    assert out2["perLens"]["my-lens"] != key_before

    # (b) unchanged view file -> stable key
    out3 = pf.compute(str(pack_dir), lenses, "HEAD~1")
    assert out3["perLens"]["my-lens"] == out2["perLens"]["my-lens"]

    # (c) full/None view reads transcript.jsonl, unaffected by the views/ edit above
    assert out2["perLens"]["full-lens"] == full_key_before


def test_compute_missing_view_file_hashes_empty_bytes_no_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(pf.lens_versions, "load_lock", lambda: {"ghost-lens": {"version": "1.0.0"}})
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir()
    # no views/ dir, no transcript.jsonl at all
    lenses = [{"skill": "ghost-lens", "model": "sonnet", "view": "nonexistent-view"}]
    out = pf.compute(str(pack_dir), lenses, "HEAD~1")
    assert out["perLens"]["ghost-lens"] == pf.lens_key(b"", "1.0.0", "sonnet", "HEAD~1")


def test_view_bytes_path_convention(tmp_path):
    pack_dir = tmp_path / "pack"
    (pack_dir / "views").mkdir(parents=True)
    (pack_dir / "views" / "activity.jsonl").write_bytes(b"activity-bytes")
    pack_dir.joinpath("transcript.jsonl").write_bytes(b"full-bytes")

    assert pf._view_bytes(str(pack_dir), "activity") == b"activity-bytes"
    assert pf._view_bytes(str(pack_dir), "full") == b"full-bytes"
    assert pf._view_bytes(str(pack_dir), None) == b"full-bytes"
    assert pf._view_bytes(str(pack_dir), "missing-view") == b""


def _run_decide(prior_path, current_path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--decide", str(prior_path), str(current_path)],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def test_decide_cli_matching_prior_reuses_all(tmp_path):
    current = {"perLens": {"a": "K1", "b": "K2"}, "whole": "W"}
    prior_path = tmp_path / "prior.json"
    current_path = tmp_path / "current.json"
    prior_path.write_text(json.dumps(current), encoding="utf-8")
    current_path.write_text(json.dumps(current), encoding="utf-8")

    out = _run_decide(prior_path, current_path)
    assert out == {"reuseAll": True, "reuse": ["a", "b"], "rerun": []}


def test_decide_cli_mismatching_prior_splits_reuse_rerun(tmp_path):
    prior = {"perLens": {"a": "K1", "b": "K2"}, "whole": "W"}
    current = {"perLens": {"a": "K1", "b": "K2-changed", "c": "K3"}, "whole": "W2"}
    prior_path = tmp_path / "prior.json"
    current_path = tmp_path / "current.json"
    prior_path.write_text(json.dumps(prior), encoding="utf-8")
    current_path.write_text(json.dumps(current), encoding="utf-8")

    out = _run_decide(prior_path, current_path)
    assert out == {"reuseAll": False, "reuse": ["a"], "rerun": ["b", "c"]}


def test_decide_cli_missing_prior_reuses_nothing(tmp_path):
    current = {"perLens": {"a": "K1", "b": "K2"}, "whole": "W"}
    prior_path = tmp_path / "does-not-exist.json"
    current_path = tmp_path / "current.json"
    current_path.write_text(json.dumps(current), encoding="utf-8")

    out = _run_decide(prior_path, current_path)
    assert out == {"reuseAll": False, "reuse": [], "rerun": ["a", "b"]}


def test_decide_cli_malformed_current_missing_perlens_exits_cleanly(tmp_path):
    prior_path = tmp_path / "prior.json"
    current_path = tmp_path / "current.json"
    prior_path.write_text(json.dumps({"perLens": {"a": "K1"}, "whole": "W"}), encoding="utf-8")
    current_path.write_text(json.dumps({"whole": "W"}), encoding="utf-8")  # no "perLens"

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--decide", str(prior_path), str(current_path)],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "perLens" in result.stderr
    # no traceback noise — a clean SystemExit message, not an unhandled KeyError
    assert "Traceback" not in result.stderr
