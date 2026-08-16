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
