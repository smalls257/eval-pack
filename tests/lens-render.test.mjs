import { test } from 'node:test';
import assert from 'node:assert';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
global.window = { __EVAL_PACK_TEST__: true };
const { effectiveConfidence, lensFindingText, renderLensTemplate, lensPath, lensValueText,
  reviewFindingsFrom, businessRiskFrom, frictionEntriesFrom,
  deliveredFrom, unmetFrom, provenFrom, unprovenFrom } = require('../templates/html/scripts.js');

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
