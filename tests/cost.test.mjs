import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import path from 'node:path';

const require = createRequire(import.meta.url);
const { estimateCost, sumReportedCost } = require(
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

// Total must equal the sum of the per-model rows shown, not lastModel-on-aggregate.
test('sumReportedCost equals the sum of per-model controller rows', () => {
  const tokensByModel = [
    { model: 'claude-opus-4-8',  inputTokens: 1000, outputTokens: 1000, cacheReadTokens: 5_000_000, cacheWriteTokens: 0 },
    { model: 'claude-sonnet-4-6', inputTokens: 1000, outputTokens: 1000, cacheReadTokens: 1_000_000, cacheWriteTokens: 0 },
  ];
  const rowsum = tokensByModel.reduce(
    (s, r) => s + estimateCost(r.model, r.inputTokens, r.outputTokens, r.cacheReadTokens, r.cacheWriteTokens), 0);
  const total = sumReportedCost(tokensByModel, [], null, null);
  assert.equal(Number(total.toFixed(4)), Number(rowsum.toFixed(4)));
});

test('sumReportedCost adds per-model subagents to controller fallback', () => {
  // no controller rows -> fallbackCtrl 0.5; subagent sonnet 1M * (3*.9+15*.1)/1e6 = 4.2
  const total = sumReportedCost([], [{ model: 'claude-sonnet-4-6', totalTokens: 1_000_000 }], 0.5, null);
  assert.equal(Number(total.toFixed(4)), 4.7);
});

test('sumReportedCost uses aggregate fallbacks when no per-model rows', () => {
  assert.equal(sumReportedCost([], [], 1.23, 0.77), 2.0);
});

test('sumReportedCost is null when there is nothing', () => {
  assert.equal(sumReportedCost([], [], null, null), null);
});
