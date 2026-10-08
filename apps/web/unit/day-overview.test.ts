import assert from 'node:assert/strict';
import { test } from 'node:test';
import { dayRows } from '../src/explorer/day-overview.ts';
const hour = 3600000;
test('history rows cover exactly elapsed time with contiguous, non-overlapping intervals', () => {
  for (const edge of [0, 8.3 * hour, 9.2 * hour, 10 * hour, 24 * hour]) {
    for (const row of dayRows(edge, 12, '2026-09-01')) {
      let last = 0;
      for (const segment of row.segments) {
        assert.equal(segment.start, last);
        assert.ok(segment.end > segment.start);
        assert.ok(segment.end <= edge);
        last = segment.end;
      }
      assert.equal(last, edge);
    }
  }
});
test('short severe delays remain visible and transport does not inherit a weather warning', () => {
  const rows = dayRows(10 * hour, 12, '2026-09-01');
  const sb = rows.find((r) => r.id === 'southbank')!;
  assert.ok(
    sb.segments.some(
      (s) =>
        s.start === 9 * hour + 10 * 60000 &&
        s.end === 9 * hour + 25 * 60000 &&
        s.tone === 'severe',
    ),
  );
  assert.equal(
    sb.segments.find((s) => s.start <= 9 * hour && s.end > 9 * hour)?.tone,
    'clear',
  );
  assert.equal(rows[0].segments.at(-1)?.tone, 'unknown');
});
test('future weather and event resolution times are hidden; DAM stays a dated snapshot', () => {
  const rows = dayRows(9.2 * hour, 12, '2026-09-01T00:00:00Z');
  assert.equal(rows[1].segments.at(-1)?.end, 9.2 * hour);
  assert.deepEqual(
    rows[2].segments.map((s) => s.tone),
    ['cloudy', 'sunny', 'cloudy', 'rainy'],
  );
  assert.equal(rows[3].segments.length, 1);
  assert.match(rows[3].segments[0].detail, /working hours.*unknown/);
  assert.match(rows[3].segments[0].detail, /2026-09-01/);
  for (const edge of [-1, NaN, 24 * hour + 1])
    assert.throws(() => dayRows(edge, 0, ''));
});
