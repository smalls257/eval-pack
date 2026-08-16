import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import pack_cost

def _sidecar(d, skill, tokens, model="sonnet", reused=False):
    (d / "lenses").mkdir(parents=True, exist_ok=True)
    (d / "lenses" / f"{skill}.cost.json").write_text(
        json.dumps({"skill": skill, "tokens": tokens, "model": model, "reused": reused}), encoding="utf-8")

def test_aggregate_sums_and_lists(tmp_path):
    _sidecar(tmp_path, "sycophancy", 44155)
    _sidecar(tmp_path, "review", 88519, model="opus")
    _sidecar(tmp_path, "eval-pack-evaluator", 51000, model="opus")
    out = pack_cost.aggregate(tmp_path)
    lenses = {e["skill"]: e for e in out["perLens"]}
    assert lenses["sycophancy"]["tokens"] == 44155
    assert out["evaluatorTokens"] == 51000        # evaluator pulled out of perLens
    assert out["totalTokens"] == 44155 + 88519 + 51000

def test_reused_lens_zero_tokens(tmp_path):
    _sidecar(tmp_path, "sycophancy", 0, reused=True)
    out = pack_cost.aggregate(tmp_path)
    e = out["perLens"][0]
    assert e["reused"] is True and e["tokens"] == 0

def test_malformed_sidecar_is_a_recorded_gap_not_zero(tmp_path):
    (tmp_path / "lenses").mkdir()
    (tmp_path / "lenses" / "friction.cost.json").write_text("{not json", encoding="utf-8")
    out = pack_cost.aggregate(tmp_path)
    e = next(x for x in out["perLens"] if x["skill"] == "friction")
    assert e["tokens"] is None and "gap" in e   # recorded gap, never silent 0
    # Finding 3: gap rows carry the same key set as normal rows so a
    # downstream consumer can do entry["model"] unconditionally.
    assert e["model"] is None and e["reused"] is None


def test_malformed_evaluator_sidecar_is_not_silently_lost(tmp_path):
    (tmp_path / "lenses").mkdir()
    (tmp_path / "lenses" / "eval-pack-evaluator.cost.json").write_text("{not json", encoding="utf-8")
    out = pack_cost.aggregate(tmp_path)
    # evaluatorTokens stays numeric (0), but the gap must be recorded
    # somewhere a caller can see it — not silently collapsed to "cost 0".
    assert out["evaluatorTokens"] == 0
    assert "eval-pack-evaluator" in out["gaps"]
    assert all(e["skill"] != "eval-pack-evaluator" for e in out["perLens"])


def test_missing_sidecar_for_expected_lens_is_a_recorded_gap(tmp_path):
    _sidecar(tmp_path, "sycophancy", 100)
    out = pack_cost.aggregate(tmp_path, expected_skills=["sycophancy", "friction"])
    lenses = {e["skill"]: e for e in out["perLens"]}
    assert lenses["sycophancy"]["tokens"] == 100
    assert lenses["friction"]["tokens"] is None
    assert lenses["friction"]["gap"] == "missing sidecar"
    assert "friction" in out["gaps"]


def test_expected_skills_none_keeps_backcompat_behavior(tmp_path):
    _sidecar(tmp_path, "sycophancy", 100)
    out = pack_cost.aggregate(tmp_path)
    assert [e["skill"] for e in out["perLens"]] == ["sycophancy"]
    assert out["gaps"] == []
