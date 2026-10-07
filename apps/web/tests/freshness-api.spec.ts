import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { AREA_ID } from '../src/city';
import { evaluatePositionFreshness } from '../src/animation/position-freshness';

test('browser freshness agrees with the server parity corpus and real API observations', async ({
  request,
}) => {
  // The Python suite checks every retained case with the production evaluator.
  // This also works in compiled serving smoke without host Python dependencies.
  const corpus = JSON.parse(
    readFileSync(
      new URL(
        '../../../tests/fixtures/position-freshness-parity.json',
        import.meta.url,
      ),
      'utf8',
    ),
  );
  for (const seconds of [0, 120, 300, 360]) {
    const response = await request.get(
      `/api/v1/areas/${AREA_ID}?scenario=city&seconds=${seconds}`,
    );
    expect(response.ok()).toBe(true);
    const view = await response.json();
    const policy = view.position_freshness_policy;
    expect(policy).toEqual(corpus.policy);
    expect(corpus.cases).toHaveLength(217);
    for (const row of corpus.cases) {
      expect(
        evaluatePositionFreshness(row.observed, row.at_ms, policy),
        JSON.stringify(row),
      ).toEqual({ status: 'ready', freshness: row.expected });
    }
    for (const vehicle of view.vehicles) {
      // Current API requests have whole-second clocks; Date is not the sub-ms oracle.
      expect(
        evaluatePositionFreshness(
          vehicle.observed_at,
          Date.parse(view.clock.at),
          policy,
        ),
      ).toEqual({ status: 'ready', freshness: vehicle.freshness });
    }
  }
});
