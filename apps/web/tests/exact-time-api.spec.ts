import { expect, test } from '@playwright/test';
import {
  firstRepresentableMillisecond,
  parseUtcMicroseconds,
  receiptEligible,
} from '../src/animation/exact-time';
import {
  AREA_ID,
  displayDateTime,
  displaySourceDate,
  displayTime,
} from '../src/city';

test('exact parser accepts real composed API view timestamps', async ({
  request,
}) => {
  // The normal test server imports fixtures into PostGIS and serves the real route.
  const response = await request.get(
    `/api/v1/areas/${AREA_ID}?scenario=city&seconds=180`,
  );
  expect(response.ok()).toBe(true);
  const snapshot = await response.json();
  const timestamps: { path: string; value: string }[] = [];
  function collect(value: unknown, path = '') {
    if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T/.test(value)) {
      timestamps.push({ path, value });
    } else if (value !== null && typeof value === 'object') {
      for (const [key, child] of Object.entries(value)) {
        // Original capture evidence deliberately retains its source spelling.
        if (key !== 'evidence') collect(child, `${path}.${key}`);
      }
    }
  }
  collect(snapshot);
  expect(timestamps.length).toBeGreaterThan(10);
  expect(
    timestamps.some(
      ({ path }) =>
        path.startsWith('.vehicles.') && path.endsWith('.observed_at'),
    ),
  ).toBe(true);
  expect(timestamps.some(({ path }) => path.endsWith('received_at'))).toBe(
    true,
  );
  expect(timestamps.some(({ path }) => path.startsWith('.weather.'))).toBe(
    true,
  );
  expect(timestamps.some(({ path }) => path.startsWith('.planning.'))).toBe(
    true,
  );
  for (const { path, value } of timestamps) {
    const exact = parseUtcMicroseconds(value);
    expect(exact, `${path}: ${value}`).not.toBeNull();
    const boundary = firstRepresentableMillisecond(exact!);
    expect(boundary).not.toBeNull();
    expect(receiptEligible(exact, boundary!)).toBe(true);
    expect(receiptEligible(exact, boundary! - 1)).toBe(false);
    // Existing UI formatting remains compatible; Date is not the exact clock oracle.
    const offset = value.replace(/Z$/, '+00:00');
    for (const format of [displayTime, displayDateTime, displaySourceDate]) {
      expect(format(value)).toBe(format(offset));
    }
  }
});
