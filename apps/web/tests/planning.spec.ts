import { expect, test } from '@playwright/test';
import { mkdir } from 'node:fs/promises';

test('city overview combines three domains and synchronizes development map/list selection', async ({
  page,
}) => {
  const external: string[] = [];
  const errors: string[] = [];
  page.on('request', (request) => {
    if (
      /^https?:/.test(request.url()) &&
      new URL(request.url()).hostname !== '127.0.0.1'
    )
      external.push(request.url());
  });
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/');
  await expect(
    page.getByRole('button', { name: 'City overview', exact: true }),
  ).toHaveAttribute('aria-pressed', 'true');
  await expect(
    page.getByRole('region', { name: 'Weather summary' }),
  ).toContainText('18 °C');
  await expect(page.getByTestId('planning-map-count')).toHaveText(
    '3 developments',
  );
  const planning = page.getByRole('region', { name: 'Planning details' });
  await expect(planning).toContainText('1 Sept 2026');
  const marker = page.getByRole('button', {
    name: 'Inspect Demo riverside development on map',
    exact: true,
  });
  await marker.click();
  await expect(planning.locator('.planning-selection')).toContainText(
    'Demo riverside development',
  );
  await expect(planning.locator('.planning-selection')).toContainText(
    'Source status: Applied',
  );
  await expect(marker).toHaveAttribute('aria-pressed', 'true');
  const row = planning.getByRole('button', {
    name: 'Inspect Demo mixed-use development in list',
    exact: true,
  });
  await row.focus();
  await row.press('Enter');
  await expect(
    page.getByRole('button', {
      name: 'Inspect Demo mixed-use development on map',
      exact: true,
    }),
  ).toHaveAttribute('aria-pressed', 'true');
  await page
    .getByRole('checkbox', { name: 'Development sites', exact: true })
    .uncheck();
  await expect(page.locator('.development-marker')).toHaveCount(0);
  await expect(
    planning
      .getByRole('group', {
        name: 'Developments inside Southbank',
        exact: true,
      })
      .getByRole('button'),
  ).toHaveCount(3);
  await page
    .getByRole('checkbox', { name: 'Development sites', exact: true })
    .check();
  await expect(page.locator('.development-marker')).toHaveCount(3);
  await mkdir('../../.local/city03', { recursive: true });
  await page.screenshot({
    path: '../../.local/city03/overview-desktop.png',
    fullPage: true,
  });
  expect(external).toEqual([]);
  expect(errors).toEqual([]);
});

test('partial, replacement, outage and recovery preserve source dates and explicit unknowns', async ({
  page,
}) => {
  await page.goto('/');
  const planning = page.getByRole('region', { name: 'Planning details' });
  await page
    .getByRole('button', { name: '120s · Partial capture', exact: true })
    .click();
  await expect(planning).toContainText('incomplete or unknown');
  await expect(planning).toContainText('1 Sept 2026');
  await expect(page.getByTestId('planning-map-count')).toHaveText(
    '3 developments',
  );
  await page
    .getByRole('button', { name: '150s · New planning snapshot', exact: true })
    .click();
  await expect(planning).toContainText('Snapshot as of 1 Oct 2026');
  await expect(
    planning
      .getByRole('group', {
        name: 'Developments inside Southbank',
        exact: true,
      })
      .getByRole('button'),
  ).toHaveCount(2);
  await expect(
    planning.getByRole('group', {
      name: 'Developments with unknown location',
      exact: true,
    }),
  ).toContainText('Demo project with missing location');
  await expect(
    page.getByRole('button', {
      name: 'Inspect Demo project with missing location on map',
      exact: true,
    }),
  ).toHaveCount(0);
  await planning
    .getByText('No longer listed in this snapshot (1)', { exact: true })
    .click();
  await expect(planning.locator('.planning-history')).toContainText(
    'Last listed as Approved',
  );
  await expect(planning.locator('.planning-history')).toContainText(
    'does not establish cancellation or completion',
  );
  await page
    .getByRole('button', { name: '240s · Planning unavailable', exact: true })
    .click();
  await expect(planning).toContainText('Planning source unavailable');
  await expect(planning).toContainText('Snapshot as of 1 Oct 2026');
  await page
    .getByRole('button', { name: '270s · Planning recovered', exact: true })
    .click();
  await expect(planning).toContainText('Snapshot as of 2 Oct 2026');
  await expect(page.getByTestId('planning-map-count')).toHaveText(
    '3 developments',
  );
  await expect(page.locator('.condition-box strong')).toHaveText('Normal');
  await page
    .getByRole('button', { name: 'Planning outage', exact: true })
    .click();
  await expect(planning).toContainText('Planning source unavailable');
  await expect(planning).toContainText('Snapshot as of 1 Sept 2026');
  await expect(page.locator('.condition-box strong')).toHaveText('Normal');
  await expect(planning.locator('.planning-history')).toHaveCount(0);
});

test('planning diagnostics and evidence preserve original captures without future data', async ({
  page,
}) => {
  await page.goto('/');
  await page
    .getByRole('button', { name: '120s · Partial capture', exact: true })
    .click();
  await expect(page.getByTestId('clock')).toHaveText('11:02:00');
  await page.getByText('Replay diagnostics', { exact: true }).click();
  await expect(
    page.getByRole('group', {
      name: 'Planning replay diagnostics',
      exact: true,
    }),
  ).toContainText('Applied 1 · Duplicates 1');
  const link = await page
    .getByRole('link', { name: 'View fixture evidence' })
    .getAttribute('href');
  const response = await page.request.get(link!);
  expect(response.status()).toBe(200);
  const data = await response.json();
  const records = data.events.filter((e: { kind: string }) =>
    e.kind.startsWith('planning-'),
  );
  expect(records.map((e: { at_seconds: number }) => e.at_seconds)).toEqual([
    0, 60, 90, 120,
  ]);
  expect(records[2].event_ids).toEqual([]);
});

for (const empty of [false, true]) {
  test(`planning ${empty ? 'complete empty snapshot' : 'missing snapshot'} has an explicit empty state`, async ({
    page,
  }) => {
    await page.route('**/api/v1/areas/*?*', async (route) => {
      const response = await route.fetch();
      const data = await response.json();
      data.planning.records = [];
      data.planning.unlocated_records = [];
      data.planning.removed_records = [];
      if (!empty) {
        data.planning.state = 'unknown';
        data.planning.snapshot_id = null;
        data.planning.as_of = null;
        data.planning.last_successful_received_at = null;
      }
      await route.fulfill({ response, json: data });
    });
    await page.goto('/');
    const planning = page.getByRole('region', { name: 'Planning details' });
    await expect(planning).toContainText(
      empty
        ? 'No located developments inside Southbank in this fixture snapshot.'
        : 'No complete snapshot received yet.',
    );
    if (!empty) await expect(planning).toContainText('Source date unknown');
    await expect(page.locator('.development-marker')).toHaveCount(0);
  });
}

test('integrated profile fits mobile and weather remains visible without scrolling', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  const summary = page.getByRole('region', { name: 'Weather summary' });
  await expect(summary).toContainText('18 °C');
  const bounds = await summary.boundingBox();
  expect(bounds!.y + bounds!.height).toBeLessThan(844);
  await expect(
    page.getByRole('region', { name: 'Planning details' }),
  ).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
  await mkdir('../../.local/city03', { recursive: true });
  await page.screenshot({
    path: '../../.local/city03/overview-mobile.png',
    fullPage: true,
  });
});
