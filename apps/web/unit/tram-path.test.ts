import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import {
  TramPath,
  interpolateTramBracket,
} from '../src/animation/tram-path.ts';
import type { MatchedObservation } from '../src/animation/tram-path.ts';

// Unequal edge lengths and a right-angle bend: fractions cannot use vertex index.
const path = new TramPath(
  'shape',
  [
    [0, 0],
    [1, 0],
    [1, 3],
  ],
  [0, 100, 400],
);
const observation = (timeMs: number, distance: number): MatchedObservation => ({
  shapeId: 'shape',
  continuityId: 'trip/component',
  observedAtUs: timeMs * 1000,
  distanceMetres: distance,
});
const from = observation(0, 0);
const to = observation(4000, 400);

test('sub-millisecond observation boundaries never become eligible early', () => {
  const start = { ...from, observedAtUs: 52_750_400 };
  const end = { ...to, observedAtUs: 53_750_400 };
  assert.equal(interpolateTramBracket(path, start, end, 52_750), null);
  const frame = interpolateTramBracket(path, start, end, 52_751)!;
  assert.equal(frame.distanceMetres, (400 * 600) / 1_000_000);
  assert.deepEqual(frame.observationTimesUs, [52_750_400, 53_750_400]);
  assert.equal(frame.label, 'Interpolated');
  assert.ok(interpolateTramBracket(path, start, end, 53_750));
  assert.equal(interpolateTramBracket(path, start, end, 53_751), null);
  for (let ms = 52_750; ms <= 53_751; ms++) {
    const direct = interpolateTramBracket(path, start, end, ms);
    interpolateTramBracket(path, start, end, 53_751);
    assert.deepEqual(interpolateTramBracket(path, start, end, ms), direct);
  }
});

test('epoch microseconds preserve fractions and reject unsafe millisecond conversion', () => {
  const epochMs = Date.UTC(2026, 9, 7);
  const start = { ...from, observedAtUs: epochMs * 1000 + 400 };
  const end = { ...to, observedAtUs: epochMs * 1000 + 1_000_400 };
  assert.equal(interpolateTramBracket(path, start, end, epochMs), null);
  assert.equal(
    interpolateTramBracket(path, start, end, epochMs + 501)?.distanceMetres,
    (400 * 500_600) / 1_000_000,
  );
  const unsafeMs = Math.floor(Number.MAX_SAFE_INTEGER / 1000) + 1;
  assert.equal(interpolateTramBracket(path, start, end, unsafeMs), null);
  const shortStart = { ...from, observedAtUs: 52_750_100 };
  const shortEnd = { ...to, observedAtUs: 52_750_900 };
  assert.equal(
    interpolateTramBracket(path, shortStart, shortEnd, 52_750),
    null,
  );
  assert.equal(
    interpolateTramBracket(path, shortStart, shortEnd, 52_751),
    null,
  );
});

test('quarter/half/three-quarter time follows distance around the bend', () => {
  for (const [time, coordinate] of [
    [1000, [1, 0]],
    [2000, [1, 1]],
    [3000, [1, 2]],
  ] as const) {
    const frame = interpolateTramBracket(path, from, to, time);
    assert.deepEqual(frame?.coordinate, coordinate);
    assert.equal(frame?.distanceMetres, time / 10);
    assert.equal(frame?.label, 'Interpolated');
  }
});

test('exact endpoints keep the Interpolated label and supporting times', () => {
  assert.deepEqual(interpolateTramBracket(path, from, to, 0), {
    coordinate: [0, 0],
    distanceMetres: 0,
    displayAtMs: 0,
    observationTimesUs: [0, 4_000_000],
    label: 'Interpolated',
  });
  assert.deepEqual(
    interpolateTramBracket(path, from, to, 4000)?.coordinate,
    [1, 3],
  );
  assert.equal(
    interpolateTramBracket(path, from, to, 4000)?.label,
    'Interpolated',
  );
});

test('an equal-distance bracket is stationary but still Interpolated', () => {
  const start = observation(10, 200),
    end = observation(5010, 200);
  for (const time of [10, 11, 2510, 5010]) {
    const frame = interpolateTramBracket(path, start, end, time);
    assert.deepEqual(frame?.coordinate, [1, 1]);
    assert.equal(frame?.label, 'Interpolated');
  }
});

test('each consecutive bracket has its own constant speed', () => {
  const middle = observation(1000, 100),
    last = observation(2000, 400);
  assert.equal(
    interpolateTramBracket(path, from, middle, 500)?.distanceMetres,
    50,
  );
  assert.equal(
    interpolateTramBracket(path, middle, last, 1500)?.distanceMetres,
    250,
  );
  assert.deepEqual(
    interpolateTramBracket(path, from, middle, 1000)?.coordinate,
    interpolateTramBracket(path, middle, last, 1000)?.coordinate,
  );
});

test('integer-millisecond seek, replay, pause and rewind are independent of frame history', () => {
  const start = observation(52400, 0),
    end = observation(52750, 400);
  const direct = interpolateTramBracket(path, start, end, 52573);
  for (const step of [1, 7, 16, 33]) {
    for (let time = 52400; time <= 52750; time += step)
      interpolateTramBracket(path, start, end, time);
    assert.deepEqual(interpolateTramBracket(path, start, end, 52573), direct);
    assert.deepEqual(interpolateTramBracket(path, start, end, 52573), direct);
  }
});

test('no extrapolation or interpolation across changed shape/continuity', () => {
  assert.equal(interpolateTramBracket(path, from, to, -1), null);
  assert.equal(interpolateTramBracket(path, from, to, 4001), null);
  for (const change of [
    { shapeId: 'other' },
    { continuityId: 'next-trip' },
    { continuityId: '' },
  ]) {
    assert.equal(
      interpolateTramBracket(path, from, { ...to, ...change }, 2000),
      null,
    );
  }
  assert.equal(
    interpolateTramBracket(path, { ...from, shapeId: 'other' }, to, 2000),
    null,
  );
});

test('invalid clocks, reversed distances and out-of-path matches cannot produce a frame', () => {
  for (const time of [NaN, Infinity, 0.5, Number.MAX_SAFE_INTEGER + 1]) {
    assert.equal(interpolateTramBracket(path, from, to, time), null);
    assert.equal(
      interpolateTramBracket(path, { ...from, observedAtUs: time }, to, 2000),
      null,
    );
  }
  assert.equal(
    interpolateTramBracket(path, observation(0, 300), observation(10, 200), 5),
    null,
  );
  assert.equal(
    interpolateTramBracket(path, from, { ...to, observedAtUs: 0 }, 0),
    null,
  );
  assert.equal(
    interpolateTramBracket(
      path,
      observation(-Number.MAX_SAFE_INTEGER, 0),
      observation(Number.MAX_SAFE_INTEGER, 400),
      0,
    ),
    null,
  );
  for (const distance of [-1, 401, NaN, Infinity]) {
    assert.equal(
      interpolateTramBracket(
        path,
        from,
        { ...to, distanceMetres: distance },
        2000,
      ),
      null,
    );
  }
});

test('coincident vertices and an entirely stationary path avoid zero-length division', () => {
  const repeated = new TramPath(
    'shape',
    [
      [0, 0],
      [0, 0],
      [1, 0],
      [1, 0],
      [1, 3],
      [1, 3],
    ],
    [0, 0, 100, 100, 400, 400],
  );
  for (const distance of [0, 25, 100, 101, 399, 400])
    assert.deepEqual(repeated.at(distance), path.at(distance));
  assert.deepEqual(
    new TramPath(
      'zero',
      [
        [1, 2],
        [1, 2],
      ],
      [0, 0],
    ).at(0),
    [1, 2],
  );
});

test('preparation and returned coordinates cannot be mutated through input/output arrays', () => {
  const coordinates = [
      [0, 0],
      [1, 0],
    ],
    distances = [0, 100];
  const prepared = new TramPath('shape', coordinates, distances);
  coordinates[1][0] = 50;
  distances[1] = 999;
  const result = prepared.at(50)!;
  result[0] = 99;
  assert.deepEqual(prepared.at(50), [0.5, 0]);
  assert.deepEqual(prepared.at(100), [1, 0]);
});

test('malformed geometry or distance indexes are rejected during preparation', () => {
  for (const [coordinates, distances] of [
    [
      [
        [0, 0],
        [0, 0],
      ],
      [0, 100],
    ],
    [
      [
        [0, 0],
        [1, 0],
        [1, 1],
      ],
      [0, 200, 100],
    ],
    [[[0, 0]], [0]],
    [
      [
        [0, 0],
        [1, 0],
      ],
      [1, 100],
    ],
    [
      [
        [0, 0],
        [1, 0],
      ],
      [0],
    ],
    [
      [
        [0, 0],
        [1, 0],
      ],
      [0, NaN],
    ],
    [
      [
        [0, 0],
        [1, 0],
      ],
      [0, -1],
    ],
    [
      [
        [0, 0],
        [1, 0],
      ],
      [0, 0],
    ],
    [
      [
        [0, 0],
        [181, 0],
      ],
      [0, 1],
    ],
    [
      [
        [0, 0],
        [1, 91],
      ],
      [0, 1],
    ],
    [
      [
        [0, 0],
        [1, NaN],
      ],
      [0, 1],
    ],
    [
      [
        [0, 0],
        [1, 0, 2],
      ],
      [0, 1],
    ],
  ] as [number[][], number[]][])
    assert.throws(() => new TramPath('shape', coordinates, distances));
  assert.throws(
    () =>
      new TramPath(
        '',
        [
          [0, 0],
          [1, 0],
        ],
        [0, 1],
      ),
  );
});

test('every retained Southbank full shape preserves all source vertices and direction', () => {
  const source = JSON.parse(
    readFileSync(
      new URL(
        '../../../tests/fixtures/map02/southbank-tram-shapes.geojson',
        import.meta.url,
      ),
      'utf8',
    ),
  );
  assert.equal(source.features.length, 208);
  for (const feature of source.features) {
    const p = new TramPath(
      feature.properties.shape_id,
      feature.geometry.coordinates,
      feature.properties.distances_m,
    );
    for (let i = 0; i < feature.properties.distances_m.length; i++) {
      assert.deepEqual(
        p.at(feature.properties.distances_m[i]),
        feature.geometry.coordinates[i],
      );
    }
  }
});
