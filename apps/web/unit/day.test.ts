import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  DAY_MS,
  WINDOW_MS,
  clockLabel,
  tramsAt,
  weatherAt,
  windowFor,
  clampClock,
} from '../src/explorer/day.ts';

test('24 hours divide into twelve non-overlapping two-hour windows', () => {
  for (let i = 0; i < 12; i++) {
    assert.equal(windowFor(i * WINDOW_MS), i * WINDOW_MS);
    assert.equal(windowFor(i * WINDOW_MS + WINDOW_MS - 1), i * WINDOW_MS);
  }
  assert.equal(windowFor(DAY_MS), DAY_MS - WINDOW_MS);
  assert.equal(clockLabel(DAY_MS), '24:00');
  assert.equal(clockLabel(8 * 3600000 + 52750, true), '08:00:52');
  assert.throws(() => clampClock(NaN));
});
test('weather is an explicit authored state, selected without future readings', () => {
  assert.equal(weatherAt(8.5 * 3600000 - 1).kind, 'sunny');
  assert.equal(weatherAt(8.5 * 3600000).kind, 'cloudy');
  assert.equal(weatherAt(9 * 3600000).kind, 'rainy');
  assert.equal(weatherAt(13 * 3600000).kind, 'sunny');
});
test('seek and playback yield identical positions and never require an unreceived sample', () => {
  for (const t of [
    0,
    1,
    59999,
    60000,
    60100,
    360001,
    7200000,
    32452750,
    DAY_MS,
  ]) {
    const before = tramsAt(t);
    tramsAt(DAY_MS - t);
    const seek = tramsAt(t);
    assert.deepEqual(before, seek);
    assert.equal(seek.length, 6);
    for (const tram of seek) {
      assert.ok(tram.pair[1] <= t);
      assert.ok(tram.pair[0] <= tram.pair[1]);
      assert.equal(tram.observed_at, null);
      assert.equal(tram.capture_ids.length, 0);
    }
  }
});
test('two observations move along the authored route and hold the first minute', () => {
  assert.deepEqual(tramsAt(0), tramsAt(59000));
  assert.notEqual(tramsAt(60000)[0].longitude, tramsAt(90000)[0].longitude);
  const a = tramsAt(359999)[0],
    b = tramsAt(360000)[0];
  assert.ok(Math.abs(a.longitude - b.longitude) < 0.000001);
});

test('preview boundary preserves the retained source geometry and credit', () => {
  const preview = JSON.parse(
    readFileSync(
      new URL('../src/assets/southbank-boundary.json', import.meta.url),
      'utf8',
    ),
  );
  const original = JSON.parse(
    readFileSync(
      new URL('../../../tests/fixtures/southbank.geojson', import.meta.url),
      'utf8',
    ),
  );
  assert.deepEqual(preview, original);
});
