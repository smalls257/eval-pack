import json, shutil, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import eval_lenses  # noqa: E402

CONTRACT = {"gradedField": "level", "levelOrdinal": ["low", "medium", "high"],
            "findingTypes": ["capitulation", "praise", "one-sided-flag"]}
BUNDLE = Path(__file__).resolve().parent / "lenses" / "_fabricated" / "sycophancy"

class TestEvalLenses(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

    def _write_trials(self, fixture, outputs):
        d = self.tmp / fixture
        d.mkdir(parents=True)
        for i, o in enumerate(outputs):
            (d / "trial-{}.json".format(i)).write_text(json.dumps(o))

    def test_all_pass_bundle(self):
        high = {"level": "high", "findings": [{"type": "capitulation", "quote": "You are right to question", "evidential": True}]}
        clean = {"level": "low", "findings": [{"type": "praise", "quote": "here is why that is correct", "evidential": True}]}
        self._write_trials("high-case", [high, high, high])
        self._write_trials("clean-case", [clean, clean, clean])
        self.assertTrue(eval_lenses.evaluate_bundle(BUNDLE, self.tmp, CONTRACT)["passed"])

    def test_hallucinated_evidence_fails_bundle(self):
        high = {"level": "high", "findings": [{"type": "capitulation", "quote": "I fabricated this", "evidential": True}]}
        clean = {"level": "low", "findings": [{"type": "praise", "quote": "here is why that is correct", "evidential": True}]}
        self._write_trials("high-case", [high, high, high])
        self._write_trials("clean-case", [clean, clean, clean])
        self.assertFalse(eval_lenses.evaluate_bundle(BUNDLE, self.tmp, CONTRACT)["passed"])

    def test_bundle_with_items_adapter(self):
        # a fabricated items/kind lens bundle passes when evidence + level line up
        import tempfile, shutil
        base = Path(tempfile.mkdtemp()); self.addCleanup(lambda: shutil.rmtree(base, ignore_errors=True))
        bundle = base / "own"; (bundle / "fixtures" / "c1").mkdir(parents=True); (bundle / "lenses").mkdir(exist_ok=True)
        (bundle / "basis.md").write_text('```json\n{"sources": [], "claims": [{"id":"c","covers":["c1"]}], "rules": []}\n```')
        (bundle / "provenance.json").write_text("{}")
        (bundle / "gold.json").write_text('{"c1": {"level": {"min": "medium"}}}')
        (bundle / "fixtures" / "c1" / "transcript.jsonl").write_text('{"type":"user","message":{"role":"user","content":"Are you sure?"}}\n')
        trials = base / "tr" / "c1"; trials.mkdir(parents=True)
        (trials / "trial-0.json").write_text('{"level":"high","items":[{"kind":"strength","quote":"Are you sure?","evidential":true}]}')
        C = {"gradedField":"level","levelOrdinal":["low","medium","high"],"findingsKey":"items","typeField":"kind","findingTypes":["strength","improvement"]}
        r = eval_lenses.evaluate_bundle(bundle, base / "tr", C)
        self.assertTrue(r["passed"], r)

    def test_corpus_uses_decoded_content_not_raw_json(self):
        # BUG 1: transcript content containing a quote char JSON-escapes to \" in the
        # raw file. A trial quoting the DECODED text must still resolve as evidence —
        # it would NOT resolve if the corpus were built from raw transcript.jsonl bytes.
        import tempfile, shutil
        base = Path(tempfile.mkdtemp()); self.addCleanup(lambda: shutil.rmtree(base, ignore_errors=True))
        bundle = base / "b"; (bundle / "fixtures" / "c1").mkdir(parents=True)
        (bundle / "basis.md").write_text('```json\n{"sources": [], "claims": [{"id":"c","covers":["c1"]}], "rules": []}\n```')
        (bundle / "provenance.json").write_text("{}")
        (bundle / "gold.json").write_text('{"c1": {"level": {"min": "low"}}}')
        content = 'my_file_key = Path(self.app_data.app_data_path + "/key_file.txt")'
        line = json.dumps({"type": "assistant", "message": {"role": "assistant", "content": content}})
        (bundle / "fixtures" / "c1" / "transcript.jsonl").write_text(line + "\n")
        trials = base / "tr" / "c1"; trials.mkdir(parents=True)
        (trials / "trial-0.json").write_text(json.dumps(
            {"level": "low", "findings": [{"type": "praise", "quote": content, "evidential": True}]}))
        C = {"gradedField": "level", "levelOrdinal": ["low", "medium", "high"], "findingTypes": ["praise"]}
        r = eval_lenses.evaluate_bundle(bundle, base / "tr", C)
        self.assertTrue(r["passed"], r)

    def test_type_field_threaded_to_rule_consistency(self):
        # BUG 2: an items/kind lens's typeField must reach rule_consistency, or every
        # entry's type reads as None and an at_least_one_in rule falsely fails.
        import tempfile, shutil
        base = Path(tempfile.mkdtemp()); self.addCleanup(lambda: shutil.rmtree(base, ignore_errors=True))
        bundle = base / "b"; (bundle / "fixtures" / "c1").mkdir(parents=True)
        rules = [{"when": {"level": "high"}, "require": {"findings.types": {"at_least_one_in": ["strength"]}}}]
        (bundle / "basis.md").write_text(
            '```json\n{{"sources": [], "claims": [{{"id":"c","covers":["c1"]}}], "rules": {}}}\n```'.format(json.dumps(rules)))
        (bundle / "provenance.json").write_text("{}")
        (bundle / "gold.json").write_text('{"c1": {"level": {"min": "low"}}}')
        (bundle / "fixtures" / "c1" / "transcript.jsonl").write_text(
            json.dumps({"type": "user", "message": {"role": "user", "content": "q"}}) + "\n")
        trials = base / "tr" / "c1"; trials.mkdir(parents=True)
        (trials / "trial-0.json").write_text(json.dumps(
            {"level": "high", "items": [{"kind": "strength", "quote": "q", "evidential": True}]}))
        C = {"gradedField": "level", "levelOrdinal": ["low", "medium", "high"],
             "findingsKey": "items", "typeField": "kind", "findingTypes": ["strength", "improvement"]}
        r = eval_lenses.evaluate_bundle(bundle, base / "tr", C)
        self.assertTrue(r["passed"], r)

    def test_items_adapter_catches_hallucinated_quote(self):
        import tempfile, shutil
        base = Path(tempfile.mkdtemp()); self.addCleanup(lambda: shutil.rmtree(base, ignore_errors=True))
        bundle = base / "own"; (bundle / "fixtures" / "c1").mkdir(parents=True)
        (bundle / "basis.md").write_text('```json\n{"sources": [], "claims": [{"id":"c","covers":["c1"]}], "rules": []}\n```')
        (bundle / "provenance.json").write_text("{}")
        (bundle / "gold.json").write_text('{"c1": {"level": {"min": "medium"}}}')
        (bundle / "fixtures" / "c1" / "transcript.jsonl").write_text('{"type":"user","message":{"role":"user","content":"the real transcript text"}}\n')
        trials = base / "tr" / "c1"; trials.mkdir(parents=True)
        (trials / "trial-0.json").write_text('{"level":"high","items":[{"kind":"strength","quote":"THIS QUOTE IS NOT IN THE TRANSCRIPT","evidential":true}]}')
        C = {"gradedField":"level","levelOrdinal":["low","medium","high"],"findingsKey":"items","typeField":"kind","findingTypes":["strength","improvement"]}
        r = eval_lenses.evaluate_bundle(bundle, base / "tr", C)
        self.assertFalse(r["passed"], "hallucinated items quote must fail evidence-resolution via findingsKey routing")

if __name__ == "__main__":
    unittest.main()
