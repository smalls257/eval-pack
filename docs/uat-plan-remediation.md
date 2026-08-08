# UAT Plan — Extensibility Remediation Surface (real sessions + Playwright)

**Target:** installed plugin `~/.claude/plugins/cache/eval-pack/eval-pack/0.3.3` @ `44132e1`.
**Fixture:** a REAL prior session transcript from `~/.claude/projects/-Users-jasonsmith-Code-eval-pack/`
(substantial, not the live session). Real artifacts, real render, browser validation via Playwright
(serve over `python3 -m http.server`; `file://` is blocked). All throwaway dirs via `mktemp -d`.
`python3` on PATH (no `python`).

**Pass bar:** every scenario has an observable expected result; a knob that "validates but changes
nothing" is a FAIL (dead knob), not a pass.

## A. Headless — real-session data through the new knobs

| ID | Scenario | Steps | Expected |
|----|----------|-------|----------|
| RS-DET-01 | `detectionPatterns` changes detection on real data | Run `detect_patterns.py --config` on the real transcript twice: (a) default config; (b) patterns that cannot match (e.g. `done: ["ZZQQXX"]`, `correction: ["ZZQQXX"]`, `retry: ["ZZQQXX"]`) | (a) records the session's real `falseCompletions`/`retryCount`; (b) both drop to 0. Counts differ ⇒ knob is live |
| RS-DET-02 | `falseCompletionWindow` + `claimTruncLen` | Same transcript, window 1 vs 5; then `claimTruncLen: 40` | count(w=5) ≥ count(w=1); every `agentClaim`/`userResponse` ≤ 40 chars |
| RS-FLAG-01 | `flagSeverities` retune + off | Real pack + `test-results.json` verdict `fail`; run with (a) `{"testsFailing":"amber"}`, (b) `{"testsFailing":"off"}` | (a) flag id `testsFailing` level amber; (b) flag absent, `flagsSuppressed` amber present, `suppressedFlags:["testsFailing"]` |
| RS-FLAG-02 | unknown verdict surfaces | verdict `banana` | `unknownVerdict` amber flag in patterns.json |
| RS-COST-01 | `costBudgetTokens` on real totals | Run `extract_metrics.py --config` on the real transcript (real `totalTokens`, likely millions); then detect_patterns with budget below and above that number | below ⇒ `overBudget` amber with real numbers in label; above ⇒ absent |
| RS-TOK-01 | `tokenWeights` on real usage | metrics with default config vs `{"cacheRead":0,"cacheWrite":0}` | weighted `totalTokens` strictly lower; default run byte-matches pre-remediation math (input+output+cacheRead+cacheWrite) |
| RS-TOK-02 | `tokenFieldNames` | Real transcript metrics with default names vs a bogus-only name (`["nonexistent_field"]`) | bogus ⇒ `subagentTotalTokens` 0 + parse warnings; default ⇒ real nonzero value |
| RS-CMD-01 | `testCommands` consumed | Temp repo, `.eval-pack.json` `testCommands: ["python3 -c 'print(\"ok\")'", "python3 -c 'raise SystemExit(1)'"]`; follow generate SKILL Step 3 as written | Step 3 instructs running EXACTLY these; real exit codes 0 and 1 captured; verdict `fail` (a command failed) — no runner guessing |
| RS-TKT-01 | `ticketPattern` consumed | Temp git repo, branch `ACME_99-widget`, `.eval-pack.json` `ticketPattern: "ACME_[0-9]+"`; execute the review skill's resolution + grep snippets verbatim | `TICKET=ACME_99`; with a broken config the `\|\| echo` fallback yields the default pattern |
| RS-GRD-01 | can-never-fail guard | `.eval-pack.json` turning exactly the 7 failure-capable flags off; run `resolve_config.py --check` | exit 0 AND stderr contains "can never fail" |

## B. Browser (Playwright) — customizations visible to a real user

| ID | Scenario | Steps | Expected |
|----|----------|-------|----------|
| PW-TPL-01 | `templateDir` restyles the report | Project dir with `mytheme/styles.css` (bundled styles.css copied + a loud override appended, e.g. `body{background:#ff00ff!important}`); config `templateDir:"mytheme"`; render real-session pack; open in browser | computed body background is the override; index.html/scripts.js still bundled (report functional); pack's styles.css contains the marker |
| PW-TPL-02 | missing templateDir fails loud | `templateDir:"does-not-exist"` | render exits 1, stderr names the dir, no pack produced |
| PW-FLAG-01 | severity retune visible | Pack from RS-FLAG-01a rendered | flags strip shows the tests flag as amber (not red) |
| PW-FLAG-02 | suppression honesty visible | Pack from RS-FLAG-01b rendered | "No flags shown — 1 suppressed by flagSeverities" amber pill visible; NO "Clean first-pass" |
| PW-COST-01 | budget flag visible | Pack from RS-COST-01 (below-budget run) rendered | `Over token budget (N > M)` amber pill with the session's real token number |
| PW-E2E-01 | combined real-session sweep | One render of the real session with: custom detectionPatterns, `flagSeverities`, budget under real total, `templateDir`, `brandName:"Remediation UAT"`, `subjectNoun:"session"` | All customizations simultaneously visible; tabs switch; zero `[object Object]`; no report JS console errors; real metrics/tools/transcript populated |

## Execution notes
- Build packs the real way: `resolve_config.py <temprepo> $PACK` (full resolved config), real
  `transcript.jsonl` via `build_conversation.py` or direct copy, `extract_metrics/detect_patterns/
  extract_tools --config`, minimal honest `analysis.json` where the evaluator isn't dispatched,
  `render_html.py $OUT $SID $PLUGIN ...` **run from the temp project dir** (templateDir resolves
  against cwd).
- Screenshot every PW scenario; grep counts for every headless assertion.
- Report per scenario: PASS/FAIL/BLOCKED + evidence; any FAIL with observed-vs-expected + file:line.
