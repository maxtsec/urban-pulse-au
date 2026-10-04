import { expect, test } from '@playwright/test';
import { mkdir } from 'node:fs/promises';

test('map and keyboard list select the same moving tram without external requests', async ({
  page,
}) => {
  const external: string[] = [];
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('request', (request) => {
    if (
      /^https?:/.test(request.url()) &&
      new URL(request.url()).hostname !== '127.0.0.1'
    )
      external.push(request.url());
  });
  await page.goto('/');
  await expect(
    page.getByRole('heading', { name: 'A closer look at Southbank.' }),
  ).toBeVisible();
  await expect(page.getByText('SYNTHETIC DEMO · NO LIVE DATA')).toBeVisible();
  const marker = page.getByRole('button', {
    name: 'Select Tram 01 on map',
    exact: true,
  });
  await expect(marker).toBeVisible();
  const before = await marker.boundingBox();
  const list = page.getByRole('button', {
    name: 'Select Tram 01 in list',
    exact: true,
  });
  await list.focus();
  await page.keyboard.press('Enter');
  await expect(marker).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByText('Tram 01 selected')).toBeVisible();
  await page.getByRole('button', { name: '30s · Position update' }).click();
  await expect(page.getByTestId('clock')).toHaveText('11:00:30');
  await expect(page.getByText(/Position: -37.82490, 144.96220/)).toBeVisible();
  const after = await marker.boundingBox();
  expect(
    Math.abs(after!.x - before!.x) + Math.abs(after!.y - before!.y),
  ).toBeGreaterThan(2);
  await page.getByRole('button', { name: 'Select Tram 02 on map' }).click();
  await expect(
    page.getByRole('button', { name: 'Select Tram 02 in list' }),
  ).toHaveAttribute('aria-pressed', 'true');
  await marker.focus();
  await page.keyboard.press('Enter');
  await expect(marker).toBeFocused();
  await expect(list).toHaveAttribute('aria-pressed', 'true');
  await page.getByRole('checkbox', { name: 'Tram positions' }).uncheck();
  await expect(marker).toHaveCount(0);
  await expect(list).toBeVisible();
  await page.getByRole('checkbox', { name: 'Tram positions' }).check();
  await expect(marker).toBeVisible();
  expect(external).toEqual([]);
  expect(errors).toEqual([]);
  await expect(
    page.getByText('Map unavailable.', { exact: false }),
  ).toHaveCount(0);
  await mkdir('../../.local/city01', { recursive: true });
  await page.screenshot({
    path: '../../.local/city01/desktop.png',
    fullPage: true,
  });
});

test('playback, stale/expired positions and missing domains remain truthful', async ({
  page,
}) => {
  await page.goto('/');
  await expect(
    page.getByRole('button', { name: 'Select Tram 01 on map' }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Play scenario' }).click();
  await expect(page.getByTestId('clock')).toHaveText('11:00:15');
  await page.getByRole('button', { name: 'Pause', exact: true }).click();
  await page.getByRole('button', { name: '150s · Stale position' }).click();
  await expect(page.getByTestId('clock')).toHaveText('11:02:30');
  await expect(
    page.getByRole('button', { name: 'Select Tram 01 on map' }),
  ).toHaveClass(/stale/);
  await expect(page.getByText('Degraded', { exact: true })).toBeVisible();
  await expect(page.getByText('Warning data not connected')).toBeVisible();
  await expect(page.getByText('Development data not connected')).toBeVisible();
  await page.getByRole('button', { name: '330s · Last known only' }).click();
  await expect(page.getByTestId('clock')).toHaveText('11:05:30');
  await expect(
    page.getByRole('button', { name: 'Select Tram 01 on map' }),
  ).toHaveCount(0);
  await expect(
    page.getByRole('button', { name: 'Select Tram 01 in list' }),
  ).toContainText('last known');
  await expect(page.getByText('Unknown', { exact: true })).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'Select Tram 03 in list' }),
  ).toContainText('Observation time unknown');
  await page.getByRole('button', { name: 'Reset', exact: true }).click();
  await expect(page.getByTestId('clock')).toHaveText('11:00:00');
});

test('empty, outage and error recovery are distinct', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Scenario', { exact: true }).selectOption('empty');
  await expect(
    page.getByText('No tram observations in this fixture view.'),
  ).toBeVisible();
  await expect(page.getByText('Unknown', { exact: true })).toBeVisible();
  await page.getByLabel('Scenario', { exact: true }).selectOption('outage');
  await page
    .getByRole('button', { name: '60s · Service interruption' })
    .click();
  await expect(page.getByText('Source unavailable · fixture')).toBeVisible();
  await expect(page.getByText('Degraded', { exact: true })).toBeVisible();
  await page.route('**/api/v1/areas/*?*', (route) =>
    route.fulfill({ status: 503, body: '{}' }),
  );
  await page.getByRole('button', { name: 'Reset', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText(
    'City snapshot unavailable',
  );
  await page.unroute('**/api/v1/areas/*?*');
  await page.getByRole('button', { name: 'Try again' }).click();
  await expect(page.getByText('Source unavailable · fixture')).toBeVisible();
});

test('boundary failure preserves the accessible observations', async ({
  page,
}) => {
  await page.route('**/boundaries/*', (route) =>
    route.fulfill({ status: 503, body: '{}' }),
  );
  await page.goto('/');
  await expect(page.getByRole('alert')).toContainText('Boundary unavailable');
  await page.getByRole('button', { name: 'Select Tram 01 in list' }).click();
  await expect(page.getByText('Tram 01 selected')).toBeVisible();
});

test('mobile layout fits and keeps the area overview usable', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await expect(
    page.getByRole('button', { name: 'Select Tram 01 on map' }),
  ).toBeVisible();
  await expect(
    page.getByRole('heading', { name: 'Southbank', exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
  await mkdir('../../.local/city01', { recursive: true });
  await page.screenshot({
    path: '../../.local/city01/mobile.png',
    fullPage: true,
  });
});
