import assert from 'node:assert/strict';
import test from 'node:test';
import {
  evaluatePositionFreshness,
  parsePositionFreshnessPolicy,
} from '../src/animation/position-freshness.ts';

const policy = {
  version: 'southbank-position-freshness-v1',
  stale_after_seconds: 120,
  expired_after_seconds: 300,
};

test('exact and fractional stale/expired boundaries compare original microseconds', () => {
  for (const [at, freshness] of [
    [119999, 'current'],
    [120000, 'stale'],
    [299999, 'stale'],
    [300000, 'expired'],
  ] as const) {
    assert.deepEqual(
      evaluatePositionFreshness('1970-01-01T00:00:00Z', at, policy),
      { status: 'ready', freshness },
    );
  }
  for (const [at, freshness] of [
    [120000, 'current'],
    [120001, 'stale'],
    [300000, 'stale'],
    [300001, 'expired'],
  ] as const) {
    assert.deepEqual(
      evaluatePositionFreshness('1970-01-01T00:00:00.000400Z', at, policy),
      { status: 'ready', freshness },
    );
  }
});

test('null and future observations are unknown; invalid data has an explicit fallback', () => {
  for (const value of [null, '1970-01-01T00:00:00.000001Z']) {
    assert.deepEqual(evaluatePositionFreshness(value, 0, policy), {
      status: 'ready',
      freshness: 'unknown',
    });
  }
  for (const value of [
    undefined,
    '',
    '1970-01-01T00:00:00+00:00',
    '1970-02-30T00:00:00Z',
  ]) {
    assert.deepEqual(evaluatePositionFreshness(value, 0, policy), {
      status: 'unavailable',
      reason: 'invalid-observation',
    });
  }
  for (const clock of [NaN, Infinity, 0.1, Number.MAX_SAFE_INTEGER + 1]) {
    assert.deepEqual(evaluatePositionFreshness(null, clock, policy), {
      status: 'unavailable',
      reason: 'invalid-clock',
    });
  }
});

test('policy validation rejects missing, unsupported, unordered and unsafe thresholds', () => {
  for (const invalid of [
    null,
    undefined,
    [],
    {},
    { ...policy, version: 'next' },
    ...[-1, 0.1, NaN, Infinity, true, '120', Number.MAX_SAFE_INTEGER + 1].map(
      (stale_after_seconds) => ({ ...policy, stale_after_seconds }),
    ),
    ...[
      0,
      119,
      120,
      300.1,
      NaN,
      Infinity,
      '300',
      Number.MAX_SAFE_INTEGER + 1,
    ].map((expired_after_seconds) => ({ ...policy, expired_after_seconds })),
  ]) {
    assert.equal(parsePositionFreshnessPolicy(invalid), null);
    assert.deepEqual(evaluatePositionFreshness(null, 0, invalid), {
      status: 'unavailable',
      reason: 'invalid-policy',
    });
  }
  const parsed = parsePositionFreshnessPolicy(policy)!;
  parsed.stale_after_seconds = 0;
  assert.equal(policy.stale_after_seconds, 120);
});

test('uses supplied thresholds rather than independent client defaults', () => {
  const supplied = {
    ...policy,
    stale_after_seconds: 0,
    expired_after_seconds: 2,
  };
  assert.deepEqual(
    evaluatePositionFreshness('1970-01-01T00:00:00Z', 0, supplied),
    { status: 'ready', freshness: 'stale' },
  );
  assert.deepEqual(
    evaluatePositionFreshness('1970-01-01T00:00:00Z', 2000, supplied),
    { status: 'ready', freshness: 'expired' },
  );
});

test('staggered vehicles can be reevaluated locally without changing their parent', () => {
  const vehicles = Array.from({ length: 100 }, (_, index) => ({
    observed_at: `1970-01-01T00:00:00.${String(index * 10000).padStart(6, '0')}Z`,
    id: index,
  }));
  const before = JSON.stringify(vehicles);
  const evaluate = (at: number) =>
    vehicles.map((v) => evaluatePositionFreshness(v.observed_at, at, policy));
  const sought = evaluate(120500);
  evaluate(120000);
  evaluate(121000);
  assert.deepEqual(evaluate(120500), sought);
  assert.equal(
    sought.filter((v) => v.status === 'ready' && v.freshness === 'stale')
      .length,
    51,
  );
  assert.equal(JSON.stringify(vehicles), before);
});
