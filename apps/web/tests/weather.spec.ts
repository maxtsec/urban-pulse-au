import { expect, test } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import {
  chooseScenario,
  closeLayers,
  condition,
  layer,
  moment,
  openTab,
  scenarioPicker,
} from './helpers';

test('weather lifecycle changes the area view and map with independent coverage', async ({
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
  await page.goto('/?scenario=weather');
  const details = page.getByRole('region', { name: 'Weather details' });
  const reasons = page.getByTestId('condition');
  await expect(
    page.getByRole('region', { name: 'Weather summary' }),
  ).toContainText('18 °C');
  await expect(condition(page)).toHaveText('Unknown');
  await moment(page, '30s · Advice').click();
  await expect(condition(page)).toHaveText('Normal');
  await openTab(page, 'Warnings');
  await expect(
    details.getByText('Informational warning; not a degradation reason.'),
  ).toBeVisible();
  await expect(page.getByTestId('warning-map-count')).toHaveText(
    '1 active warning area',
  );
  await (await layer(page, 'Warning areas')).uncheck();
  await expect(page.getByTestId('warning-map-count')).toHaveCount(0);
  await expect(details.getByRole('article')).toHaveCount(1);
  await (await layer(page, 'Warning areas')).check();
  await closeLayers(page);
  await moment(page, '60s · Watch and Act').click();
  await expect(condition(page)).toHaveText('Degraded');
  await expect(reasons).toContainText('2 active reasons');
  await moment(page, '150s · Cancelled').click();
  await expect(details.getByText('cancelled', { exact: true })).toBeVisible();
  await expect(reasons).toContainText('1 active reason');
  await expect(page.getByTestId('warning-map-count')).toHaveText(
    '0 active warning areas',
  );
  await moment(page, '180s · Emergency Warning').click();
  await expect(reasons).toContainText('1 active reason');
  await expect(page.getByTestId('warning-map-count')).toHaveText(
    '1 active warning area',
  );
  await openTab(page, 'Overview');
  await expect(page.locator('.reason')).toHaveCount(1);
  await expect(page.locator('.reason')).toContainText('Emergency Warning');
  await mkdir('../../.local/city02', { recursive: true });
  await page.screenshot({
    path: '../../.local/city02/weather-desktop.png',
    fullPage: true,
  });
  await openTab(page, 'Warnings');
  await moment(page, '240s · Expired, coverage stale').click();
  await expect(condition(page)).toHaveText('Unknown');
  await expect(details.locator('.warning-heading').first()).toContainText(
    'stale',
  );
  await expect(details.getByText('expired', { exact: true })).toBeVisible();
  await moment(page, '270s · Coverage restored').click();
  await expect(condition(page)).toHaveText('Normal');
  await moment(page, '330s · Incomplete coverage').click();
  await expect(condition(page)).toHaveText('Unknown');
  await expect(details.getByText(/Area applicability unknown/)).toBeVisible();
  expect(errors).toEqual([]);
  expect(external).toEqual([]);
});

test('outage keeps received warning and attribution without leaking cancellation', async ({
  page,
}) => {
  await page.goto('/?scenario=weather');
  await chooseScenario(page, 'Weather outage');
  await moment(page, '180s · Emergency Warning').click();
  await openTab(page, 'Warnings');
  const details = page.getByRole('region', { name: 'Weather details' });
  await expect(condition(page)).toHaveText('Degraded');
  await expect(
    details.getByText('Watch and Act', { exact: true }),
  ).toBeVisible();
  await expect(details).not.toContainText('cancelled');
  await expect(details.locator('.weather-credit')).toContainText(
    'State of Victoria',
  );
  await expect(
    details.getByRole('link', { name: 'EMV emergency-data notice' }),
  ).toHaveAttribute(
    'href',
    'https://www.emv.vic.gov.au/responsibilities/victorias-warning-system/emergency-data',
  );
  await expect(details.locator('.weather-receipt')).toContainText('11:01:00');
  await expect(details.locator('.weather-receipt')).toContainText('2026');
  await expect(details.locator('.weather-receipt')).toContainText(
    /AEDT|GMT\+11/,
  );
  await moment(page, '240s · Expired, coverage stale').click();
  await expect(condition(page)).toHaveText('Unknown');
  await expect(details.locator('.weather-receipt')).toContainText('11:01:00');
  await expect(details.locator('.warning-heading').first()).toContainText(
    'error',
  );
});

test('weather details are usable on a small screen and replay keeps original receipt date', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/?scenario=weather');
  await moment(page, '270s · Coverage restored').click();
  await expect(condition(page)).toHaveText('Normal');
  await moment(page, '30s · Advice').click();
  await openTab(page, 'Warnings');
  await expect(page.locator('.weather-receipt')).toContainText('11:00:30');
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await mkdir('../../.local/city02', { recursive: true });
  await page.screenshot({
    path: '../../.local/city02/weather-mobile.png',
    fullPage: true,
  });
});

for (const viewport of [
  { width: 1440, height: 900 },
  { width: 390, height: 844 },
]) {
  test(`weather and conditions are on the map on arrival at ${viewport.width}px`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    await page.goto('/?scenario=weather');
    await expect(scenarioPicker(page)).toHaveValue('weather');
    const summary = page.getByRole('region', { name: 'Weather summary' });
    await expect(summary).toContainText('18 °C');
    const map = (await page.locator('.map-area').boundingBox())!;
    for (const overlay of [summary, page.getByTestId('condition')]) {
      const bounds = (await overlay.boundingBox())!;
      expect(bounds.y).toBeGreaterThanOrEqual(map.y);
      expect(bounds.y + bounds.height).toBeLessThan(viewport.height);
      expect(bounds.x + bounds.width).toBeLessThanOrEqual(viewport.width);
    }
    expect(map.height).toBeGreaterThan(viewport.height * 0.6);
    expect(await page.evaluate(() => window.scrollY)).toBe(0);
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(viewport.width);
    await mkdir('../../.local/city02', { recursive: true });
    await page.screenshot({
      path: `../../.local/city02/arrival-${viewport.width}.png`,
      fullPage: true,
    });
  });
}

test('scenario picker supports keyboard selection and preserves the chosen clock', async ({
  page,
}) => {
  await page.goto('/?scenario=weather');
  await moment(page, '60s · Watch and Act').click();
  const picker = scenarioPicker(page);
  await picker.focus();
  // Weather warnings is followed by Tram journey in the picker order.
  await page.keyboard.press('ArrowDown');
  await expect(picker).toHaveValue('journey');
  await expect(page.getByTestId('clock')).toHaveText('11:01:00');
  await expect(
    page.getByRole('region', { name: 'Weather summary' }),
  ).toContainText('not included');
  await chooseScenario(page, 'Weather warnings');
  await expect(picker).toHaveValue('weather');
  await expect(
    page.getByRole('region', { name: 'Weather summary' }),
  ).toContainText('18 °C');
  await expect(page.getByTestId('clock')).toHaveText('11:01:00');
});

for (const scenario of ['weather', 'weather-outage']) {
  test(`${scenario} with no reading keeps weather context`, async ({
    page,
  }) => {
    await page.route('**/api/v1/areas/*?*', async (route) => {
      const response = await route.fetch();
      const data = await response.json();
      data.weather.reading = null;
      await route.fulfill({ response, json: data });
    });
    await page.goto(`/?scenario=${scenario}`);
    const summary = page.getByRole('region', { name: 'Weather summary' });
    await expect(summary).toContainText('No modelled weather reading received');
    await expect(summary).not.toContainText('transport scenario');
    await openTab(page, 'Warnings');
    await expect(
      page.getByRole('region', { name: 'Weather details' }),
    ).toBeVisible();
  });
}

test('scenario navigation updates shareable URLs and supports browser history', async ({
  page,
}) => {
  await page.goto('/?scenario=weather&example=keep#demo');
  const summary = page.getByRole('region', { name: 'Weather summary' });
  await expect(summary).toContainText('18 °C');
  await chooseScenario(page, 'Tram journey');
  await expect(page).toHaveURL(/scenario=journey&example=keep#demo$/);
  await expect(summary).toContainText('transport scenario');
  await page.goBack();
  await expect(scenarioPicker(page)).toHaveValue('weather');
  await expect(summary).toContainText('18 °C');
  await page.goForward();
  await expect(scenarioPicker(page)).toHaveValue('journey');
  await page.reload();
  await expect(scenarioPicker(page)).toHaveValue('journey');
  await expect(summary).toContainText('transport scenario');
  await chooseScenario(page, 'Weather warnings');
  await expect(page).toHaveURL(/scenario=weather&example=keep#demo$/);
});

test('scenario transition preserves the map canvas and camera while labelling previous data', async ({
  page,
}) => {
  await page.goto('/?scenario=weather');
  const canvas = page.locator('.maplibregl-canvas');
  await expect(canvas).toBeVisible();
  const original = await canvas.elementHandle();
  const marker = page.locator('.maplibregl-marker').first();
  await expect(marker).toBeVisible();
  const initial = await marker.getAttribute('style');
  await page.getByRole('button', { name: 'Zoom in', exact: true }).click();
  await expect(marker).not.toHaveAttribute('style', initial!);
  const bounds = await canvas.boundingBox();
  await page.mouse.move(
    bounds!.x + bounds!.width / 3,
    bounds!.y + bounds!.height / 2,
  );
  await page.mouse.down();
  await page.mouse.move(
    bounds!.x + bounds!.width / 3 + 30,
    bounds!.y + bounds!.height / 2 + 20,
    { steps: 10 },
  );
  await page.mouse.up();
  // Allow the zoom and drag inertia animations to settle before comparing camera position.
  await page.waitForTimeout(1000);
  const cameraPosition = await marker.getAttribute('style');
  let release!: () => void;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route('**/api/v1/areas/*?*scenario=journey', async (route) => {
    await held;
    await route.continue();
  });
  await chooseScenario(page, 'Tram journey');
  await expect(
    page.getByText('Loading scenario… Still showing Weather warnings.'),
  ).toBeVisible();
  expect(await original!.evaluate((node) => node.isConnected)).toBe(true);
  await expect(
    page.getByRole('button', { name: 'Play scenario', exact: true }),
  ).toBeDisabled();
  release();
  await expect(
    page.getByRole('region', { name: 'Weather summary' }),
  ).toContainText('transport scenario');
  await expect(page.getByText(/Loading scenario…/)).toHaveCount(0);
  expect(await original!.evaluate((node) => node.isConnected)).toBe(true);
  await expect(marker).toHaveAttribute('style', cameraPosition!);
});

test('replay diagnostics separate weather duplicates from transport counts', async ({
  page,
}) => {
  await page.goto('/?scenario=weather');
  await expect(page.getByTestId('clock')).toHaveText('11:00:00');
  await page.getByLabel('Scenario time', { exact: true }).fill('120');
  await expect(page.getByTestId('clock')).toHaveText('11:02:00');
  await page.getByText('Replay diagnostics', { exact: true }).click();
  await expect(
    page.getByRole('group', {
      name: 'Weather replay diagnostics',
      exact: true,
    }),
  ).toContainText('Duplicates 2');
  await expect(
    page.getByRole('group', {
      name: 'Transport replay diagnostics',
      exact: true,
    }),
  ).toContainText('Applied');
  await chooseScenario(page, 'Tram journey');
  await expect(
    page.getByRole('region', { name: 'Weather summary' }),
  ).toContainText('transport scenario');
  await expect(
    page.getByRole('group', {
      name: 'Weather replay diagnostics',
      exact: true,
    }),
  ).toHaveCount(0);
  await expect(
    page.getByRole('group', {
      name: 'Transport replay diagnostics',
      exact: true,
    }),
  ).toBeVisible();
});
