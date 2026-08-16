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
