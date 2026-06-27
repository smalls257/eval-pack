import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import path from 'node:path';

const require = createRequire(import.meta.url);
const { screenshotBadge, wrapIndex } = require(
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
