import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import path from 'node:path';

const require = createRequire(import.meta.url);
const { estimateCost } = require(
  path.join(import.meta.dirname, '..', 'templates', 'html', 'scripts.js')
);

// opus rates: in=15, out=75 per 1M. cache write=1.25x in, read=0.10x in.
test('estimateCost includes cache write and read', () => {
  // (100*15 + 100*75 + 100*15*1.25 + 1000*15*0.10)/1e6
  // = (1500 + 7500 + 1875 + 1500)/1e6 = 0.012375
  const c = estimateCost('claude-opus-4-8', 100, 100, 1000, 100);
  assert.equal(Number(c.toFixed(6)), 0.012375);
});

test('cache-read dominated cost is far above input+output only', () => {
  const withCache = estimateCost('claude-opus-4-8', 100, 100, 1_000_000, 0);
  const noCache = estimateCost('claude-opus-4-8', 100, 100, 0, 0);
  // 1M cache reads at 0.10*15 = $1.50, dwarfing the $0.009 input/output
  assert.ok(withCache > noCache + 1.4);
});

test('missing cache args default to zero (back-compat)', () => {
  const c = estimateCost('claude-opus-4-8', 100, 100);
  assert.equal(Number(c.toFixed(6)), 0.009); // (1500+7500)/1e6
});

test('zero everything returns null', () => {
  assert.equal(estimateCost('claude-opus-4-8', 0, 0, 0, 0), null);
});
