import { readFileSync } from 'node:fs';
import { expect, test } from '@playwright/test';

test('full day keeps evenly spaced two-hour controls, weather and accessible selection', async ({
  page,
}) => {
  const apis: string[] = [];
  page.on('request', (r) => {
    if (r.url().includes('/api/')) apis.push(r.url());
  });
  await page.goto('/?experience=day');
  await expect(page.getByRole('heading', { name: 'Southbank' })).toBeVisible();
  await expect(
    page
      .getByRole('group', { name: 'Choose two-hour window' })
      .getByRole('button'),
  ).toHaveCount(12);
  await expect(page.locator('.even-ticks')).toHaveText(
    '08:0008:3009:0009:3010:00',
  );
  await page.getByLabel('History time').fill(String(9 * 3600000));
  await expect(page.getByTestId('day-clock')).toHaveText('09:00:00');
  await expect(page.locator('.city-glance')).toContainText('rainy');
  await page.getByRole('button', { name: '22:00 to 24:00' }).click();
  await expect(page.getByTestId('day-clock')).toHaveText('22:00:00');
  await page
    .getByRole('button', { name: '6 trams Simulated movement' })
    .click();
  const row = page.getByRole('button', { name: 'Tram 1 Track A', exact: true });
  await row.focus();
  await page.keyboard.press('Enter');
  await expect(row).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByRole('button', { name: 'Play demo' })).toBeDisabled();
  expect(apis).toEqual([]);
});
test('3D local models and rain load, layers toggle and fallback keeps selection', async ({
  page,
}) => {
  const errors: string[] = [],
    external: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('request', (r) => {
    if (/^https?:/.test(r.url()) && new URL(r.url()).hostname !== '127.0.0.1')
      external.push(r.url());
  });
  await page.goto('/?experience=day');
  await page.getByRole('button', { name: '3D', exact: true }).click();
  await expect(page.getByTestId('map')).toHaveAttribute('data-models', 'ready');
  await expect(
    page.getByRole('button', { name: 'Select Tram 1 on map', exact: true }),
  ).toHaveCount(0);
  await page.getByLabel('History time').fill(String(9 * 3600000));
  await expect(page.locator('.weather-atmosphere')).toHaveClass(/rainy/);
  await page.getByRole('button', { name: 'Layers', exact: true }).click();
  await page.getByRole('checkbox', { name: 'weather', exact: true }).uncheck();
  await expect(page.locator('.weather-atmosphere')).toHaveCount(0);
  await page.getByRole('button', { name: '2D', exact: true }).click();
  await expect(
    page.getByRole('button', { name: 'Select Tram 1 on map', exact: true }),
  ).toBeVisible();
  expect(errors).toEqual([]);
  expect(external).toEqual([]);
});
test('history pause, seek, speed and simulated live work without affecting fixture API', async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await page.goto('/?experience=day');
  await page
    .getByRole('combobox', { name: 'Playback speed' })
    .selectOption('300');
  await page.getByRole('button', { name: 'Play demo' }).click();
  await expect(page.getByTestId('day-clock')).not.toHaveText('08:00:00');
  await page.getByRole('button', { name: 'Pause demo' }).click();
  const stopped = await page.getByTestId('day-clock').innerText();
  await page.waitForTimeout(200);
  await expect(page.getByTestId('day-clock')).toHaveText(stopped);
  await page.getByRole('button', { name: 'Live', exact: true }).click();
  await expect(page.locator('.player-context')).toHaveText(
    'Simulated live · 1×',
  );
  await expect(
    page.getByRole('combobox', { name: 'Playback speed' }),
  ).toBeDisabled();
  await page.getByRole('button', { name: 'History', exact: true }).click();
  await expect(
    page.getByRole('combobox', { name: 'Playback speed' }),
  ).toBeEnabled();
});
test('mobile opens with a compact static 2D summary and usable day controls', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/?experience=day');
  await expect(page.getByTestId('map')).toHaveAttribute('data-view', '2d');
  await expect(
    page.getByRole('region', { name: 'City summary' }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.getByRole('button', { name: '12:00 to 14:00' }).click();
  await expect(page.getByTestId('day-clock')).toHaveText('12:00:00');
});

test('model loading obeys the deployed CSP and failed assets retain usable markers', async ({
  page,
}) => {
  const policy = readFileSync(
    new URL('../Caddyfile', import.meta.url),
    'utf8',
  ).match(/Content-Security-Policy "([^"]+)"/)![1];
  const violations: string[] = [];
  page.on('console', (m) => {
    if (/Content Security Policy|violates.*directive/i.test(m.text()))
      violations.push(m.text());
  });
  await page.route('**/*', async (route) => {
    if (route.request().resourceType() !== 'document') return route.continue();
    const response = await route.fetch();
    await route.fulfill({
      response,
      headers: { ...response.headers(), 'content-security-policy': policy },
    });
  });
  await page.goto('/?experience=day');
  await page.getByRole('button', { name: '3D', exact: true }).click();
  await expect(page.getByTestId('map')).toHaveAttribute('data-models', 'ready');
  expect(violations).toEqual([]);
  await page.route('**/demo-tram*.glb', (route) =>
    route.fulfill({ status: 503, body: 'unavailable' }),
  );
  await page.reload();
  await page.getByRole('button', { name: '3D', exact: true }).click();
  await expect(
    page.getByText('3D models unavailable.', { exact: false }),
  ).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'Select Tram 1 on map', exact: true }),
  ).toBeVisible();
});
test('missing buildings do not prevent models and WebGL recovery uses the selected time', async ({
  page,
}) => {
  await page.route('**/southbank-buildings*.geojson', (route) =>
    route.fulfill({ status: 503, body: 'unavailable' }),
  );
  await page.goto('/?experience=day');
  await page.getByRole('button', { name: '3D', exact: true }).click();
  await expect(page.getByTestId('map')).toHaveAttribute('data-models', 'ready');
  await expect(
    page.getByText('Buildings unavailable.', { exact: false }),
  ).toBeVisible();
  const extension = await page
    .getByTestId('map')
    .locator('canvas')
    .evaluateHandle((canvas: HTMLCanvasElement) =>
      canvas.getContext('webgl2')!.getExtension('WEBGL_lose_context')!,
    );
  await extension.evaluate((e) => e.loseContext());
  await expect(
    page.getByText('Map unavailable.', { exact: false }),
  ).toBeVisible();
  await page.getByLabel('History time').fill(String(9 * 3600000));
  await extension.evaluate((e) => e.restoreContext());
  await expect(
    page.getByText('Map unavailable.', { exact: false }),
  ).toHaveCount(0);
  await expect(page.getByTestId('map')).toHaveAttribute('data-models', 'ready');
  await expect(page.getByTestId('day-clock')).toHaveText('09:00:00');
  await page.getByRole('button', { name: '2D', exact: true }).click();
  await expect(
    page.getByRole('button', { name: 'Select Tram 1 on map', exact: true }),
  ).toBeVisible();
  await extension.dispose();
});
