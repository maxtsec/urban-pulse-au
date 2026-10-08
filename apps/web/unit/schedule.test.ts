import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import { scheduledDistance, makeSchedule } from '../src/explorer/schedule.ts';
import type { SampleData, Stop } from '../src/explorer/schedule.ts';
const data = JSON.parse(
  readFileSync(
    new URL('../src/assets/sample/city.json', import.meta.url),
    'utf8',
  ),
) as SampleData;
test('schedule preserves dwell, interpolates only between stops, and does not extrapolate', () => {
  const stops: Stop[] = [
    [0, 10000, 0],
    [70000, 80000, 120],
    [140000, 140000, 240],
  ];
  assert.equal(scheduledDistance(stops, -1), null);
  assert.equal(scheduledDistance(stops, 5000), 0);
  assert.equal(scheduledDistance(stops, 40000), 60);
  assert.equal(scheduledDistance(stops, 75000), 120);
  assert.equal(scheduledDistance(stops, 110000), 180);
  assert.equal(scheduledDistance(stops, 140000), null);
});
test('same-minute published times use the last scheduled position deterministically', () => {
  const stops: Stop[] = [
    [0, 0, 0],
    [60000, 60000, 100],
    [60000, 60000, 150],
    [120000, 120000, 200],
  ];
  assert.equal(scheduledDistance(stops, 59999)! < 100, true);
  assert.equal(scheduledDistance(stops, 60000), 150);
});
test('real schedule supports arbitrary seeking without observed claims or invented routes', () => {
  const schedule = makeSchedule(data);
  for (const clock of [
    0,
    52750,
    3600000,
    8 * 3600000,
    9 * 3600000,
    23 * 3600000,
    86400000,
  ]) {
    const direct = schedule.at(clock);
    schedule.at(86400000 - clock);
    assert.deepEqual(schedule.at(clock), direct);
    for (const tram of direct) {
      assert.equal(tram.observed_at, null);
      assert.deepEqual(tram.capture_ids, []);
      assert.match(tram.id, /^schedule:/);
      assert.notEqual(tram.route_id, 'A');
    }
  }
  assert.ok(schedule.at(9 * 3600000).length > 20);
  assert.equal(schedule.at(86400000).length >= 0, true);
});
