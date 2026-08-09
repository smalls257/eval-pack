# Lens evaluation — the live N-trial dispatch runbook

The lens evaluator has two modes. **The CI gate is deterministic and offline**: it replays the
committed `trials/` through the pure engine (`tests/test_real_bundles_e2e.py` →
`eval_lenses.evaluate_bundle`). **This runbook is the other mode** — the *live measurement loop* that
dispatches the real lens to produce fresh trials. It needs a live LLM, so it is a documented
procedure, not a unit test. Run it when a lens prompt changes, to see whether the current lens still
scores its gold fixtures correctly.

## What a bundle is

```
tests/lenses/<lens>/
  basis.md          # sources + claims + rules (structured ```json block) + prose
  provenance.json   # resolved-source ledger (offline gate reads this)
  gold.json         # per-fixture expected assertions (score band | level ordinal | findings set)
  fixtures/<case>/
    transcript.jsonl        # the session (ask + turns)
    meta.json               # source, license, attribution
    base/  delivered.patch  # (diff-needing lenses only) the pre-image + the delivered change
  trials/<case>/trial-<k>.json   # recorded lens outputs (what the gate replays)
```

## Live dispatch — regenerate `trials/`

For each fixture, dispatch the lens **N=3 times** (Schmid's "run several, look at the distribution")
and collect each output as a trial.

1. **Load the fixture.** For a diff-needing lens (e.g. `requirement-drift`):

   ```python
   import sys; sys.path.insert(0, "scripts")
   from fixture_loader import load_fixture
   from pathlib import Path
   fx = Path("tests/lenses/requirement-drift/fixtures/cog-complexity-15-resolved")
   with load_fixture(fx) as (pack_dir, repo_root, diff_base):
       ...  # dispatch the lens here, inside the with-block (repo_root is a temp repo)
   ```

   For a transcript-only lens (e.g. `sycophancy`), `repo_root`/`diff_base` are `None` and `pack_dir`
   is the fixture dir itself.

2. **Dispatch the lens subagent**, seeded with the working-repo `agents/lenses/<lens>.md`, given
   `PACK_DIR` (= `pack_dir`), `REPO_ROOT`, `DIFF_BASE`. The lens reads `PACK_DIR/transcript.jsonl`
   and (diff lenses) runs `git -C "$REPO_ROOT" diff "$DIFF_BASE"`. **Every finding's `quote` MUST be
   a verbatim substring of the transcript or the diff** — the gate resolves quotes literally, so a
   paraphrase or a conflated span (e.g. combining a code line with an issue gloss) will fail
   evidence-resolution. Non-evidential/proposing findings set `evidential: false, quote: null`.

3. **Collect** each run's output JSON to `trials/<case>/trial-<k>.json` (k = 0..N-1).

4. **Evaluate:**

   ```python
   from eval_lenses import evaluate_bundle
   contract = {"gradedField": "score", "findingTypes": ["unmet","unrequested","met"]}  # per lens .md
   b = Path("tests/lenses/requirement-drift")
   report = evaluate_bundle(b, b / "trials", contract)
   print(report["passed"], report["checks"], report["fixtures"])
   ```

   A fixture passes when ≥2/3 trials meet its gold assertion, every evidential finding's quote
   resolves, and the output obeys the lens's declared `rules`. The bundle passes when all fixtures
   pass and the per-bundle checks (reference-resolution, claim-coverage) pass.

5. **Commit** the refreshed `trials/` once the bundle passes. The offline gate now replays them.

## Refresh the provenance ledger

`basis.md` cites vetted sources; `provenance.json` is the resolved snapshot the offline gate compares
against. To refresh it against the live web, resolve each source's citation (arXiv/DOI/HTTP) and feed
the results to the pure builder:

```python
from refresh_sources import build_ledger
import json
sources = json.loads(...)  # basis.md's ```json block -> ["sources"]
def resolve(citation):
    ...  # hit arXiv/DOI here, return {"title", "authors", "date"}
ledger = build_ledger(sources, resolve)   # stamp resolved_at in the CLI, then write provenance.json
```

If a live resolve disagrees with `basis.md`'s declared title, reference-resolution will fail on the
next gate run — that is the check catching a fabricated or drifted citation. Fix the basis or the
ledger, don't silence the check.

## Scope note (as of Part 3)

Only `requirement-drift` and `sycophancy` ship bundles. The other graded lenses declare an output
contract (Part 2) but are not yet evaluated; the three narrative-only lenses
(`friction`/`repo-improvements`/`review`) are out of scope until they'd be evaluated. Adding a new
lens's evaluation = dropping a new `tests/lenses/<lens>/` bundle and recording its trials via this
runbook.
