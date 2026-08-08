import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import path from 'node:path';

const require = createRequire(import.meta.url);
const { screenshotBadge, wrapIndex, zoomAt, artifactHref, artifactLinkable, computeBaseFit } = require(
  path.join(import.meta.dirname, '..', 'templates', 'html', 'scripts.js')
);

test('screenshotBadge maps known sources', () => {
  assert.deepEqual(screenshotBadge('agent'), { text: 'Agent-captured', cls: 'badge-agent' });
  assert.deepEqual(screenshotBadge('test'), { text: 'Automated test', cls: 'badge-test' });
});

test('screenshotBadge falls back to unknown for missing/unrecognized source', () => {
  assert.deepEqual(screenshotBadge(undefined), { text: 'Unknown source', cls: 'badge-unknown' });
  assert.deepEqual(screenshotBadge('nonsense'), { text: 'Unknown source', cls: 'badge-unknown' });
});

test('wrapIndex wraps forward past the end', () => {
  assert.equal(wrapIndex(3, 3), 0);
  assert.equal(wrapIndex(4, 3), 1);
});

test('wrapIndex wraps backward past the start', () => {
  assert.equal(wrapIndex(-1, 3), 2);
  assert.equal(wrapIndex(-2, 3), 1);
});

test('wrapIndex is safe for an empty set', () => {
  assert.equal(wrapIndex(0, 0), 0);
  assert.equal(wrapIndex(-1, 0), 0);
});

// The point under the cursor must stay fixed across a zoom (m = pan + scale*p).
test('zoomAt keeps the cursor point fixed', () => {
  const { scale, panX } = zoomAt(1, 0, 0, 100, 0, 2, 5);
  assert.equal(scale, 2);
  // before: cursor m=100 at scale 1, pan 0 -> image-local p = 100
  // after:  pan + scale*p = -100 + 2*100 = 100 (unchanged)
  assert.equal(panX, -100);
  assert.equal(panX + scale * 100, 100);
});

test('zoomAt clamps to maxScale', () => {
  assert.equal(zoomAt(4, 0, 0, 0, 0, 2, 5).scale, 5);
});

test('zoomAt clamps to 1 and resets pan', () => {
  assert.deepEqual(zoomAt(1.2, 50, 30, 0, 0, 0.1, 5), { scale: 1, panX: 0, panY: 0 });
});

test('zoomAt about centre (cursor 0,0) keeps pan zero', () => {
  assert.deepEqual(zoomAt(1, 0, 0, 0, 0, 2, 5), { scale: 2, panX: 0, panY: 0 });
});

// Raw .jsonl is excluded from the pack; transcript ships as transcript.html.
test('artifactHref maps transcript.jsonl to the shipped transcript.html', () => {
  assert.equal(artifactHref('transcript.jsonl'), 'transcript.html');
  assert.equal(artifactHref('metrics.json'), 'metrics.json');
  assert.equal(artifactHref('screenshots/a.png'), 'screenshots/a.png');
});

test('artifactLinkable: transcript ok, other .jsonl not, normal files ok', () => {
  assert.equal(artifactLinkable('transcript.jsonl'), true);   // has transcript.html stand-in
  assert.equal(artifactLinkable('merged.jsonl'), false);      // excluded, no stand-in -> no dead link
  assert.equal(artifactLinkable('metrics.json'), true);
  assert.equal(artifactLinkable('screenshots/x.png'), true);
  assert.equal(artifactLinkable('//evil'), false);            // unsafe path
});

// computeBaseFit: the zoom=1 display factor that fits a NATURAL-size image into the
// stage box (letterboxing, aspect preserved) — the factor baked into the transform
// alongside the user's zoom `scale` so the backing raster never gets downsampled by
// layout before scale() is applied.
test('computeBaseFit: wide image (4:1) constrained by stage width', () => {
  // natural 4000x1000, stage 1000x1000 -> width ratio 0.25, height ratio 1.0 -> min is width
  assert.equal(computeBaseFit(4000, 1000, 1000, 1000), 0.25);
});

test('computeBaseFit: tall image (1:4) constrained by stage height', () => {
  // natural 1000x4000, stage 1000x1000 -> width ratio 1.0, height ratio 0.25 -> min is height
  assert.equal(computeBaseFit(1000, 4000, 1000, 1000), 0.25);
});

test('computeBaseFit: image smaller than stage still scales (up or down) to fit exactly', () => {
  assert.equal(computeBaseFit(500, 500, 1000, 1000), 2);
});

test('computeBaseFit: falls back to 1 when natural dimensions are not yet known (0/NaN)', () => {
  assert.equal(computeBaseFit(0, 0, 1000, 1000), 1);
  assert.equal(computeBaseFit(NaN, 500, 1000, 1000), 1);
  assert.equal(computeBaseFit(500, 500, 0, 0), 1);
});
