import { test } from 'node:test';
import assert from 'node:assert';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
global.window = { __EVAL_PACK_TEST__: true };

// Minimal DOM stub — just enough for renderImprovements/renderPromptPattern to run
// end-to-end against a fake element registry, without pulling in a real DOM library.
function makeFakeDocument(ids) {
  const elements = {};
  for (const id of ids) {
    elements[id] = { innerHTML: '', textContent: '', style: {} };
  }
  return {
    elements,
    getElementById(id) { return elements[id] || null; },
  };
}

const { effectiveConfidence, lensFindingText, renderLensTemplate, lensPath, lensValueText,
  reviewFindingsFrom, businessRiskFrom, frictionEntriesFrom, diffReposFrom,
  repoImprovementsFrom, userImprovementsFrom, sessionArtifactsFrom,
  deliveredFrom, unmetFrom, provenFrom, unprovenFrom,
  testResultsSummary, renderImprovements, renderPromptPattern, renderDiff, lensTabsFrom,
  lensCardsFrom } = require('../templates/html/scripts.js');

test('effectiveConfidence uses finalScore when a non-core rule ran scorers', () => {
  const analysis = { highlights: { confidencePercent: 90 } };
  const lenses = { rule: 'min', coreScore: 90, finalScore: 61, scorers: [{ skill: 'x', score: 61 }] };
  assert.deepStrictEqual(effectiveConfidence(analysis, lenses),
    { value: 61, note: 'min of core 90 and 1 scorer lens(es)' });
});

test('effectiveConfidence falls back to core when no scorers or rule core', () => {
  const analysis = { highlights: { confidencePercent: 90 } };
  assert.deepStrictEqual(effectiveConfidence(analysis, null), { value: 90, note: null });
  assert.deepStrictEqual(
    effectiveConfidence(analysis, { rule: 'core', coreScore: 90, scorers: [] }),
    { value: 90, note: null });
});

test('lensFindingText handles strings and {type,detail} objects', () => {
  assert.strictEqual(lensFindingText('plain finding'), 'plain finding');
  assert.strictEqual(lensFindingText({ type: 'unmet', detail: 'missed the ask' }),
    'unmet: missed the ask');
  assert.strictEqual(lensFindingText({ detail: 'just detail' }), 'just detail');
  assert.strictEqual(lensFindingText(42), '42');
});

test('lensFindingText renders verification-rigor claim shape readably', () => {
  assert.strictEqual(
    lensFindingText({ claim: 'tests pass', backed: true, evidence: 'Ran 216 tests OK' }),
    '✓ tests pass — Ran 216 tests OK');
  assert.strictEqual(
    lensFindingText({ claim: 'done', backed: false, evidence: 'none' }),
    '✗ done');
});

test('lensFindingText never emits raw JSON for unknown objects', () => {
  const out = lensFindingText({ foo: 'bar', n: 2 });
  assert.ok(!out.includes('{'), out);
  assert.strictEqual(out, 'foo: bar · n: 2');
});

test('renderLensTemplate escapes interpolated values, preserves markup', () => {
  const out = renderLensTemplate('<b>{{rationale}}</b>', { rationale: '<script>x</script>' });
  assert.strictEqual(out, '<b>&lt;script&gt;x&lt;/script&gt;</b>');
});

test('renderLensTemplate sections iterate arrays with {{.}} and item fields', () => {
  const out = renderLensTemplate('<ul>{{#findings}}<li>{{.}}|{{type}}</li>{{/findings}}</ul>',
    { findings: [{ type: 'met', detail: 'ok' }] });
  assert.strictEqual(out, '<ul><li>met: ok|met</li></ul>');
});

test('renderLensTemplate unknown fields empty, dot paths work', () => {
  assert.strictEqual(renderLensTemplate('{{nope}}[{{a.b}}]', { a: { b: 5 } }), '[5]');
});

test('renderLensTemplate non-array section renders empty', () => {
  assert.strictEqual(renderLensTemplate('{{#x}}boom{{/x}}', { x: 'not-array' }), '');
});

test('reviewFindingsFrom reads findings from the review contributor', () => {
  const lenses = {
    contributors: [
      { skill: 'other', role: 'contributor', title: 'Other', findings: [{ x: 1 }] },
      { skill: 'review', role: 'contributor', title: 'Review Findings', findings: [
        { severity: 'critical', issue: 'off-by-one', foundIn: 'a.py' },
      ] },
    ],
  };
  assert.deepStrictEqual(reviewFindingsFrom(lenses), [
    { severity: 'critical', issue: 'off-by-one', foundIn: 'a.py' },
  ]);
});

test('reviewFindingsFrom degrades to empty list when the lens is absent (Airplane Test)', () => {
  assert.deepStrictEqual(reviewFindingsFrom(null), []);
  assert.deepStrictEqual(reviewFindingsFrom({ contributors: [] }), []);
  assert.deepStrictEqual(reviewFindingsFrom({ contributors: [{ skill: 'other', findings: [{ x: 1 }] }] }), []);
});

test('businessRiskFrom reads the business-risk contributor', () => {
  const lenses = {
    contributors: [
      { skill: 'other', role: 'contributor', title: 'Other' },
      { skill: 'business-risk', role: 'contributor', title: 'Business Risk',
        level: 'high', notes: 'wide blast radius', mitigation: ['add a feature flag'],
        mainRisk: 'rollback path is untested' },
    ],
  };
  assert.deepStrictEqual(businessRiskFrom(lenses), {
    skill: 'business-risk', role: 'contributor', title: 'Business Risk',
    level: 'high', notes: 'wide blast radius', mitigation: ['add a feature flag'],
    mainRisk: 'rollback path is untested',
  });
});

test('businessRiskFrom degrades to null when the lens is absent (Airplane Test)', () => {
  assert.strictEqual(businessRiskFrom(null), null);
  assert.strictEqual(businessRiskFrom({ contributors: [] }), null);
  assert.strictEqual(businessRiskFrom({ contributors: [{ skill: 'other' }] }), null);
});

test('frictionEntriesFrom reads entries from the friction contributor', () => {
  const lenses = {
    contributors: [
      { skill: 'other', role: 'contributor', title: 'Other', entries: [{ x: 1 }] },
      { skill: 'friction', role: 'contributor', title: 'Friction Log', entries: [
        { friction: 'CI flaked twice', impact: 'wasted 20 minutes', type: 'tooling' },
      ] },
    ],
  };
  assert.deepStrictEqual(frictionEntriesFrom(lenses), [
    { friction: 'CI flaked twice', impact: 'wasted 20 minutes', type: 'tooling' },
  ]);
});

test('frictionEntriesFrom degrades to empty list when the lens is absent (Airplane Test)', () => {
  assert.deepStrictEqual(frictionEntriesFrom(null), []);
  assert.deepStrictEqual(frictionEntriesFrom({ contributors: [] }), []);
  assert.deepStrictEqual(frictionEntriesFrom({ contributors: [{ skill: 'other', entries: [{ x: 1 }] }] }), []);
});

test('diffReposFrom degrades to empty buckets when repoDiffs is absent (Airplane Test)', () => {
  assert.deepStrictEqual(diffReposFrom(null), { repos: [], skipped: [], errors: [] });
  assert.deepStrictEqual(diffReposFrom({}), { repos: [], skipped: [], errors: [] });
  assert.deepStrictEqual(diffReposFrom({ repoDiffs: {} }), { repos: [], skipped: [], errors: [] });
});

test('diffReposFrom passes through populated repoDiffs buckets', () => {
  const data = {
    repoDiffs: {
      repos: [{ repoRoot: '/r', branch: 'main', base: 'HEAD', baseResolved: 'abc123def456', insertions: 3, deletions: 1, filesChanged: 2, files: ['a.py', 'b.py'], stat: ' a.py | 2 +-' }],
      skipped: [{ repoRoot: '/s', reason: 'user skipped' }],
      errors: [{ repoRoot: '/e', base: 'HEAD', error: 'not a git repo' }],
    },
  };
  assert.deepStrictEqual(diffReposFrom(data), data.repoDiffs);
});

test('sessionArtifactsFrom degrades to empty list when artifactInventory is absent (Airplane Test)', () => {
  assert.deepStrictEqual(sessionArtifactsFrom(null), []);
  assert.deepStrictEqual(sessionArtifactsFrom({}), []);
  assert.deepStrictEqual(sessionArtifactsFrom({ artifactInventory: undefined }), []);
});

test('sessionArtifactsFrom passes through the deterministic artifactInventory', () => {
  const data = {
    artifactInventory: [
      { name: 'Transcript', path: 'transcript.html', type: 'transcript', description: 'Rendered conversation' },
      { name: 'metrics.json', path: 'metrics.json', type: 'data', description: 'Session metrics' },
    ],
  };
  assert.strictEqual(sessionArtifactsFrom(data), data.artifactInventory);
});

// Render-level XSS regression: a malicious repoRoot from repo-diffs.json must be escaped by
// renderDiff before it reaches innerHTML — a raw <script> would be a stored-XSS Silent Fallback
// where the render "succeeds" but injects executable markup.
test('renderDiff escapes a malicious repoRoot instead of injecting raw markup', () => {
  const fakeDoc = makeFakeDocument(['diff-body']);
  const restore = global.document;
  global.document = fakeDoc;
  try {
    renderDiff({
      repoDiffs: {
        repos: [{ repoRoot: '<script>alert(1)</script>', branch: 'main', base: 'x', baseResolved: 'y',
          insertions: 0, deletions: 0, filesChanged: 0, files: [], stat: '' }],
        skipped: [],
        errors: [],
      },
    });
    const out = fakeDoc.elements['diff-body'].innerHTML;
    assert.ok(out.includes('&lt;script&gt;'), out);
    assert.ok(!out.includes('<script>'), out);
  } finally {
    global.document = restore;
  }
});

test('repoImprovementsFrom reads items from the repo-improvements contributor', () => {
  const lenses = {
    contributors: [
      { skill: 'other', role: 'contributor', title: 'Other', items: [{ x: 1 }] },
      { skill: 'repo-improvements', role: 'contributor', title: 'Repo Improvements', items: [
        { title: 'Add schema-sync test', detail: 'Prevents config.py and the schema drifting.' },
      ] },
    ],
  };
  assert.deepStrictEqual(repoImprovementsFrom(lenses), [
    { title: 'Add schema-sync test', detail: 'Prevents config.py and the schema drifting.' },
  ]);
});

test('repoImprovementsFrom degrades to empty list when the lens is absent (Airplane Test)', () => {
  assert.deepStrictEqual(repoImprovementsFrom(null), []);
  assert.deepStrictEqual(repoImprovementsFrom({ contributors: [] }), []);
  assert.deepStrictEqual(repoImprovementsFrom({ contributors: [{ skill: 'other', items: [{ x: 1 }] }] }), []);
});

test('userImprovementsFrom reads the full user-improvements contributor record, including promptPattern', () => {
  const lenses = {
    contributors: [
      { skill: 'other', role: 'contributor', title: 'Other' },
      { skill: 'user-improvements', role: 'contributor', title: 'User Improvements',
        items: [{ title: 'Name files up front', detail: 'Saved two turns of grepping.' }],
        promptPattern: 'Update templates/html/scripts.js to add X' },
    ],
  };
  assert.deepStrictEqual(userImprovementsFrom(lenses), {
    skill: 'user-improvements', role: 'contributor', title: 'User Improvements',
    items: [{ title: 'Name files up front', detail: 'Saved two turns of grepping.' }],
    promptPattern: 'Update templates/html/scripts.js to add X',
  });
});

test('userImprovementsFrom degrades to null when the lens is absent (Airplane Test)', () => {
  assert.strictEqual(userImprovementsFrom(null), null);
  assert.strictEqual(userImprovementsFrom({ contributors: [] }), null);
  assert.strictEqual(userImprovementsFrom({ contributors: [{ skill: 'other' }] }), null);
});

test('deliveredFrom/unmetFrom read the requirement-drift SCORER lens (not a contributor)', () => {
  const lenses = {
    scorers: [
      { skill: 'other', role: 'scorer', score: 50 },
      { skill: 'requirement-drift', role: 'scorer', score: 72,
        delivered: ['Added the login form'], unmet: ['Password reset was never wired up'] },
    ],
  };
  assert.deepStrictEqual(deliveredFrom(lenses), ['Added the login form']);
  assert.deepStrictEqual(unmetFrom(lenses), ['Password reset was never wired up']);
});

test('deliveredFrom/unmetFrom degrade to empty list when the lens is absent (Airplane Test)', () => {
  assert.deepStrictEqual(deliveredFrom(null), []);
  assert.deepStrictEqual(deliveredFrom({ scorers: [] }), []);
  assert.deepStrictEqual(deliveredFrom({ scorers: [{ skill: 'other', delivered: ['x'] }] }), []);
  assert.deepStrictEqual(unmetFrom(null), []);
  assert.deepStrictEqual(unmetFrom({ scorers: [] }), []);
  assert.deepStrictEqual(unmetFrom({ scorers: [{ skill: 'other', unmet: ['x'] }] }), []);
});

test('provenFrom/unprovenFrom read the verification-rigor SCORER lens (not a contributor)', () => {
  const lenses = {
    scorers: [
      { skill: 'other', role: 'scorer', score: 50 },
      { skill: 'verification-rigor', role: 'scorer', score: 84,
        proven: ['Test suite ran green (293 py + 26 node)'],
        unproven: ['Claimed the UI "looks right" with no screenshot'] },
    ],
  };
  assert.deepStrictEqual(provenFrom(lenses), ['Test suite ran green (293 py + 26 node)']);
  assert.deepStrictEqual(unprovenFrom(lenses), ['Claimed the UI "looks right" with no screenshot']);
});

test('provenFrom/unprovenFrom degrade to empty list when the lens is absent (Airplane Test)', () => {
  assert.deepStrictEqual(provenFrom(null), []);
  assert.deepStrictEqual(provenFrom({ scorers: [] }), []);
  assert.deepStrictEqual(provenFrom({ scorers: [{ skill: 'other', proven: ['x'] }] }), []);
  assert.deepStrictEqual(unprovenFrom(null), []);
  assert.deepStrictEqual(unprovenFrom({ scorers: [] }), []);
  assert.deepStrictEqual(unprovenFrom({ scorers: [{ skill: 'other', unproven: ['x'] }] }), []);
});

test('testResultsSummary reads verdict/summary/testsRun from the deterministic test-results.json', () => {
  const testResults = {
    verdict: 'pass',
    summary: '8 tests passed',
    testsRun: [{ name: 'auth.test.ts', passed: true, output: '8 passed' }],
  };
  assert.deepStrictEqual(testResultsSummary(testResults), {
    verdict: 'pass',
    summary: '8 tests passed',
    testsRun: [{ name: 'auth.test.ts', passed: true, output: '8 passed' }],
  });
});

test('testResultsSummary degrades to null when test-results.json is absent/empty (Airplane Test)', () => {
  assert.strictEqual(testResultsSummary(null), null);
  assert.strictEqual(testResultsSummary(undefined), null);
  assert.strictEqual(testResultsSummary({}), null);
});

test('testResultsSummary tolerates a verdict with no per-test records (no crash, no evidence-cluster fields)', () => {
  assert.deepStrictEqual(testResultsSummary({ verdict: 'none' }), {
    verdict: 'none',
    summary: '',
    testsRun: [],
  });
});

test('lensTabsFrom returns [] for absent/empty/dedicated-only lenses', () => {
  assert.deepStrictEqual(lensTabsFrom(null), []);
  assert.deepStrictEqual(lensTabsFrom({}), []);
  assert.deepStrictEqual(
    lensTabsFrom({ contributors: [{ skill: 'friction', role: 'contributor' }] }), []);
});

test('lensTabsFrom surfaces scorers then non-dedicated contributors then failures, in order', () => {
  const tabs = lensTabsFrom({
    scorers: [{ skill: 'requirement-drift', role: 'scorer', score: 93 },
              { skill: 'verification-rigor', role: 'scorer', score: 90 }],
    contributors: [{ skill: 'friction', role: 'contributor' },
                   { skill: 'my-custom', role: 'contributor', title: 'My Custom' }],
    failures: [{ skill: 'broken-lens', error: 'boom' }],
  });
  assert.deepStrictEqual(tabs.map(t => [t.kind, t.panelId, t.label]), [
    ['scorer',      'lens-requirement-drift',  'Requirement Drift'],
    ['scorer',      'lens-verification-rigor', 'Verification Rigor'],
    ['contributor', 'lens-my-custom',          'My Custom'],
    ['failure',     'lens-broken-lens',        'Broken Lens'],
  ]);
});

test('lensCardsFrom maps a display:"card" business-risk contributor to a card descriptor', () => {
  const lenses = { contributors: [
    { skill: 'business-risk', role: 'contributor', display: 'card', level: 'medium',
      notes: 'redaction off by default', mitigation: ['safe default ruleset'],
      mainRisk: 'raw transcript published' },
  ] };
  const cards = lensCardsFrom(lenses);
  assert.strictEqual(cards.length, 1);
  const c = cards[0];
  assert.strictEqual(c.label, 'Business Risk');
  assert.strictEqual(c.value, 'Medium');
  assert.strictEqual(c.level, 'medium');
  assert.strictEqual(c.note, 'redaction off by default');
  assert.deepStrictEqual(c.items, ['safe default ruleset', 'main risk: raw transcript published']);
  // a card must NOT also become a tab
  assert.deepStrictEqual(lensTabsFrom(lenses), []);
});

test('lensCardsFrom maps a display:"card" scorer using its numeric score', () => {
  const lenses = { scorers: [
    { skill: 'x', role: 'scorer', score: 88, display: 'card', rationale: 'ok' },
  ] };
  const cards = lensCardsFrom(lenses);
  assert.strictEqual(cards.length, 1);
  assert.strictEqual(cards[0].value, 88);
  assert.strictEqual(cards[0].level, null);
  assert.strictEqual(cards[0].note, 'ok');
  assert.strictEqual(cards[0].kind, 'scorer');
});

test('lensCardsFrom ignores records with no display or display:"tab"; those stay tabs', () => {
  const lenses = { scorers: [
    { skill: 'a', role: 'scorer', score: 50 },              // no display
    { skill: 'b', role: 'scorer', score: 60, display: 'tab' },
  ] };
  assert.deepStrictEqual(lensCardsFrom(lenses), []);
  assert.deepStrictEqual(lensTabsFrom(lenses).map(t => t.panelId), ['lens-a', 'lens-b']);
});

test('lensCardsFrom degrades to [] for absent/empty lenses (Airplane Test)', () => {
  assert.deepStrictEqual(lensCardsFrom(null), []);
  assert.deepStrictEqual(lensCardsFrom({}), []);
});

// Render-level: a display:'card' business-risk lens is injected into #highlights-row with its
// level class, and its untrusted values are ESCAPED (no raw <script> reaches innerHTML).
test('renderLenses injects card lenses into the highlights row and escapes their values', () => {
  const require2 = createRequire(import.meta.url);
  const { renderLenses } = require2('../templates/html/scripts.js');
  const row = { children: [], appendChild(el) { this.children.push(el); } };
  const nav = { querySelector() { return null; }, insertBefore() {} };
  const elements = {
    'highlights-row': row,
    'tab-nav': nav,
    'session-artifacts': { parentNode: { insertBefore() {} } },
  };
  const fakeDoc = {
    getElementById(id) { return elements[id] || null; },
    createElement() { return { className: '', innerHTML: '', appendChild() {} }; },
  };
  const restore = global.document;
  global.document = fakeDoc;
  try {
    renderLenses({ lenses: { contributors: [
      { skill: 'business-risk', role: 'contributor', display: 'card', level: 'high',
        notes: '<script>alert(1)</script>', mitigation: ['flag it'], mainRisk: 'boom' },
    ] } });
    assert.strictEqual(row.children.length, 1);
    const card = row.children[0];
    assert.match(card.className, /biz-risk-high/);
    assert.match(card.innerHTML, /Business Risk/);
    assert.match(card.innerHTML, /&lt;script&gt;/);       // escaped
    assert.ok(!card.innerHTML.includes('<script>'), card.innerHTML);
    assert.match(card.innerHTML, /flag it/);
    assert.match(card.innerHTML, /main risk: boom/);
  } finally {
    global.document = restore;
  }
});

// Transparency guard: the core → final aggregation math must render even when EVERY lens is
// configured display:'card', so lensTabsFrom returns [] and no lens tab panel exists to host it.
test('renderLenses renders the aggregation line even when there are no lens tabs', () => {
  const require2 = createRequire(import.meta.url);
  const { renderLenses } = require2('../templates/html/scripts.js');
  const row = { children: [], appendChild(el) { this.children.push(el); } };
  const nav = { querySelector() { return null; }, insertBefore() {} };
  const aggLine = { innerHTML: '' };
  const elements = {
    'highlights-row': row,
    'lens-agg-line': aggLine,
    'tab-nav': nav,
    'session-artifacts': { parentNode: { insertBefore() {} } },
  };
  const fakeDoc = {
    getElementById(id) { return elements[id] || null; },
    createElement() { return { className: '', innerHTML: '', appendChild() {} }; },
  };
  const restore = global.document;
  global.document = fakeDoc;
  try {
    const data = { lenses: {
      finalScore: 82, coreScore: 82, rule: 'core',
      scorers: [{ skill: 'requirement-drift', score: 82, display: 'card' }],
      contributors: [], failures: [],
    } };
    assert.strictEqual(lensTabsFrom(data.lenses).length, 0);  // all lenses are cards → zero tabs
    renderLenses(data);
    assert.match(aggLine.innerHTML, /Verdict aggregation/);
    assert.match(aggLine.innerHTML, /82/);
  } finally {
    global.document = restore;
  }
});

test('lensTabsFrom de-dupes colliding panel ids', () => {
  const tabs = lensTabsFrom({ scorers: [
    { skill: 'a/b', score: 1 }, { skill: 'a-b', score: 2 } ] });
  assert.deepStrictEqual(tabs.map(t => t.panelId), ['lens-a-b', 'lens-a-b-2']);
});

// e2e: render a pack whose lenses include repo-improvements.json and user-improvements.json
// output — both tabs render content sourced from the lenses (not from any evaluator field),
// and promptPattern shows from the SAME user-improvements lens record.
test('renderImprovements/renderPromptPattern render tab content from lens output', () => {
  const ids = ['repo-improvements-list', 'user-improvements-list', 'prompt-pattern-area', 'prompt-pattern'];
  const fakeDoc = makeFakeDocument(ids);
  const restore = global.document;
  global.document = fakeDoc;
  try {
    const data = {
      lenses: {
        contributors: [
          { skill: 'repo-improvements', role: 'contributor', title: 'Repo Improvements', items: [
            { title: 'Add CI lint step', detail: 'Would have caught the trailing whitespace earlier.' },
          ] },
          { skill: 'user-improvements', role: 'contributor', title: 'User Improvements',
            items: [{ title: 'Name the target file', detail: 'Saved a round of grepping.' }],
            promptPattern: 'Update scripts/config.py to add the new lens defaults' },
        ],
      },
    };
    renderImprovements(data);
    renderPromptPattern(data);

    assert.match(fakeDoc.elements['repo-improvements-list'].innerHTML, /Add CI lint step/);
    assert.match(fakeDoc.elements['repo-improvements-list'].innerHTML, /trailing whitespace/);
    assert.match(fakeDoc.elements['user-improvements-list'].innerHTML, /Name the target file/);
    assert.strictEqual(fakeDoc.elements['prompt-pattern-area'].style.display, 'block');
    assert.strictEqual(fakeDoc.elements['prompt-pattern'].textContent,
      'Update scripts/config.py to add the new lens defaults');
  } finally {
    global.document = restore;
  }
});

// Airplane Test for the render path: none of the 3 old evaluator fields exist AND neither
// new lens file exists — no crash, both tabs show their empty-state, prompt-pattern-area
// stays hidden exactly as it did before the decomposition.
test('renderImprovements/renderPromptPattern degrade to empty-state with no lenses and no legacy evaluator fields (Airplane Test)', () => {
  const ids = ['repo-improvements-list', 'user-improvements-list', 'prompt-pattern-area', 'prompt-pattern'];
  const fakeDoc = makeFakeDocument(ids);
  const restore = global.document;
  global.document = fakeDoc;
  try {
    const data = { analysis: {} }; // no repoImprovements/userImprovements/promptPattern, no lenses
    assert.doesNotThrow(() => {
      renderImprovements(data);
      renderPromptPattern(data);
    });
    assert.match(fakeDoc.elements['repo-improvements-list'].innerHTML, /empty-state/);
    assert.match(fakeDoc.elements['repo-improvements-list'].innerHTML, /No improvements recorded/);
    assert.match(fakeDoc.elements['user-improvements-list'].innerHTML, /empty-state/);
    assert.strictEqual(fakeDoc.elements['prompt-pattern-area'].style.display, 'none');
  } finally {
    global.document = restore;
  }
});
