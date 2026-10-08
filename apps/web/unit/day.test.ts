import { MeshoptDecoder } from '../src/explorer/meshopt-disabled.ts';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  DAY_MS,
  liveEdgeAt,
  historyClock,
  availableWindow,
  WINDOW_MS,
  clockLabel,
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

test('live edge bounds both window selection and seeking, while retaining a full-day scale', () => {
  assert.equal(liveEdgeAt(0), 36000000);
  assert.equal(liveEdgeAt(1500), 36001500);
  assert.equal(liveEdgeAt(DAY_MS), DAY_MS);
  assert.equal(historyClock(DAY_MS, 36001500), 36001500);
  assert.deepEqual(availableWindow(36000000, 36001500), {
    start: 36000000,
    end: 36001500,
  });
  assert.deepEqual(availableWindow(28800000, 36001500), {
    start: 28800000,
    end: 36000000,
  });
});

test('original models need no compressed decoder and unsupported compression fails explicitly', async () => {
  await MeshoptDecoder.ready;
  assert.equal(MeshoptDecoder.supported, false);
  assert.throws(() => MeshoptDecoder.decodeGltfBuffer(), /not supported/);
  for (const name of ['tram', 'crane', 'planned']) {
    const bytes = readFileSync(
      new URL(`../src/assets/demo-${name}.glb`, import.meta.url),
    );
    const json = JSON.parse(
      bytes.subarray(20, 20 + bytes.readUInt32LE(12)).toString('utf8'),
    );
    assert.deepEqual(json.extensionsRequired ?? [], []);
    assert.deepEqual(json.extensionsUsed ?? [], []);
  }
});
