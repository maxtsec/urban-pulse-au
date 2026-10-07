import assert from 'node:assert/strict';
import test from 'node:test';
import {
  firstRepresentableMillisecond,
  millisecondsToMicroseconds,
  parseUtcMicroseconds,
  receiptEligible,
  safeObservationMicroseconds,
} from '../src/animation/exact-time.ts';
import {
  TramPath,
  interpolateTramBracket,
} from '../src/animation/tram-path.ts';

test('zero through six fractional digits preserve exact microseconds', () => {
  assert.equal(parseUtcMicroseconds('1970-01-01T00:00:00Z'), 0n);
  for (let digits = 1; digits <= 6; digits++) {
    const fraction = '123456'.slice(0, digits);
    assert.equal(
      parseUtcMicroseconds(`1970-01-01T00:00:00.${fraction}Z`),
      BigInt(fraction.padEnd(6, '0')),
    );
  }
  assert.equal(parseUtcMicroseconds('1969-12-31T23:59:59.999999Z'), -1n);
});

test('Gregorian dates validate leap years and do not inherit Date year remapping', () => {
  assert.equal(
    parseUtcMicroseconds('0001-01-01T00:00:00Z'),
    -62135596800000000n,
  );
  assert.equal(
    parseUtcMicroseconds('9999-12-31T23:59:59.999999Z'),
    253402300799999999n,
  );
  assert.equal(
    parseUtcMicroseconds('2000-03-01T00:00:00Z')! -
      parseUtcMicroseconds('2000-02-28T00:00:00Z')!,
    2n * 86400n * 1_000_000n,
  );
  assert.equal(
    parseUtcMicroseconds('1900-03-01T00:00:00Z')! -
      parseUtcMicroseconds('1900-02-28T00:00:00Z')!,
    86400n * 1_000_000n,
  );
  assert.equal(parseUtcMicroseconds('1900-02-29T00:00:00Z'), null);
});

test('calendar arithmetic agrees with an independent whole-second Date oracle', () => {
  for (const year of [
    1, 4, 100, 400, 1600, 1900, 1970, 2000, 2026, 2100, 2400, 9999,
  ]) {
    for (let month = 0; month < 12; month++) {
      const calendar = new Date(0);
      calendar.setUTCFullYear(year, month, 28);
      calendar.setUTCHours(23, 59, 58, 0);
      const timestamp = calendar.toISOString().replace('.000Z', '.123456Z');
      assert.equal(
        parseUtcMicroseconds(timestamp),
        BigInt(calendar.getTime()) * 1000n + 123456n,
      );
    }
  }
});

test('invalid dates, noncanonical UTC and excess precision fail instead of normalizing', () => {
  for (const timestamp of [
    null,
    undefined,
    0,
    true,
    '',
    '2026-02-29T00:00:00Z',
    '2026-04-31T00:00:00Z',
    '0000-01-01T00:00:00Z',
    '2026-00-01T00:00:00Z',
    '2026-13-01T00:00:00Z',
    '2026-01-00T00:00:00Z',
    '2026-01-01T24:00:00Z',
    '2026-01-01T00:60:00Z',
    '2026-01-01T00:00:60Z',
    '2026-01-01T00:00:00.Z',
    '2026-01-01T00:00:00.0000001Z',
    '2026-01-01T00:00:00+00:00',
    '2026-01-01T00:00:00-00:00',
    '2026-01-01t00:00:00z',
    ' 2026-01-01T00:00:00Z',
    '2026-01-01T00:00:00Z\n',
  ]) {
    assert.equal(parseUtcMicroseconds(timestamp), null, String(timestamp));
  }
});

test('safe millisecond clocks convert before multiplication and never round', () => {
  assert.equal(
    millisecondsToMicroseconds(Number.MAX_SAFE_INTEGER),
    BigInt(Number.MAX_SAFE_INTEGER) * 1000n,
  );
  for (const invalid of [NaN, Infinity, 0.5, Number.MAX_SAFE_INTEGER + 1]) {
    assert.equal(millisecondsToMicroseconds(invalid), null);
    assert.equal(receiptEligible(0n, invalid), false);
  }
});

test('receipt gating and ceiling boundaries agree on positive and negative fractions', () => {
  for (const timestamp of [
    -1001n,
    -1000n,
    -999n,
    -1n,
    0n,
    1n,
    999n,
    1000n,
    1001n,
    52_750_400n,
  ]) {
    const first = firstRepresentableMillisecond(timestamp)!;
    assert.equal(receiptEligible(timestamp, first - 1), false);
    assert.equal(receiptEligible(timestamp, first), true);
  }
  assert.equal(receiptEligible(null, 0), false);
  assert.equal(
    firstRepresentableMillisecond(BigInt(Number.MAX_SAFE_INTEGER) * 1000n + 1n),
    null,
  );
});

test('number bridge rejects epochs outside the interpolation safe range', () => {
  for (const value of [
    -BigInt(Number.MAX_SAFE_INTEGER),
    0n,
    BigInt(Number.MAX_SAFE_INTEGER),
  ]) {
    assert.equal(BigInt(safeObservationMicroseconds(value)!), value);
  }
  assert.equal(
    safeObservationMicroseconds(BigInt(Number.MAX_SAFE_INTEGER) + 1n),
    null,
  );
  assert.equal(
    safeObservationMicroseconds(-BigInt(Number.MAX_SAFE_INTEGER) - 1n),
    null,
  );
  assert.equal(safeObservationMicroseconds(null), null);
});

test('one exact parse supports both receipt eligibility and interpolation brackets', () => {
  const firstUs = parseUtcMicroseconds('2026-10-07T00:00:52.750400Z')!;
  const lastUs = parseUtcMicroseconds('2026-10-07T00:00:53.750400Z')!;
  const anchorMs = firstRepresentableMillisecond(lastUs)!;
  assert.equal(receiptEligible(firstUs, anchorMs), true);
  assert.equal(receiptEligible(lastUs, anchorMs - 1), false);
  assert.equal(receiptEligible(lastUs, anchorMs), true);
  const path = new TramPath(
    'shape',
    [
      [0, 0],
      [1, 0],
    ],
    [0, 100],
  );
  const from = {
    shapeId: 'shape',
    continuityId: 'trip',
    observedAtUs: safeObservationMicroseconds(firstUs)!,
    distanceMetres: 0,
  };
  const to = {
    ...from,
    observedAtUs: safeObservationMicroseconds(lastUs)!,
    distanceMetres: 100,
  };
  // After both receipts are eligible, the delayed display still uses exact observation time.
  const firstDisplayMs = firstRepresentableMillisecond(firstUs)!;
  assert.equal(
    interpolateTramBracket(path, from, to, firstDisplayMs - 1),
    null,
  );
  assert.equal(
    interpolateTramBracket(path, from, to, firstDisplayMs)?.distanceMetres,
    0.06,
  );
  assert.deepEqual(
    interpolateTramBracket(path, from, to, firstDisplayMs)?.observationTimesUs,
    [Number(firstUs), Number(lastUs)],
  );
});
