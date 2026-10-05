import { expect, test } from '@playwright/test';
import { mkdir } from 'node:fs/promises';

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
  await page
    .getByRole('group', { name: 'Scenario', exact: true })
    .getByRole('button', { name: 'Weather warnings', exact: true })
    .click();
  const details = page.getByRole('region', { name: 'Weather details' });
  await expect(
    page
      .getByRole('region', { name: 'Weather summary' })
      .getByText('Modelled weather information'),
  ).toBeVisible();
  await expect(page.locator('.condition-box strong')).toHaveText('Unknown');
  await page.getByRole('button', { name: '30s · Advice', exact: true }).click();
  await expect(page.locator('.condition-box strong')).toHaveText('Normal');
  await expect(
    details.getByText('Informational warning; not a degradation reason.'),
  ).toBeVisible();
  await expect(page.getByTestId('warning-map-count')).toHaveText(
    '1 active warning areas',
  );
  await page
    .getByRole('checkbox', { name: 'Warning areas', exact: true })
    .uncheck();
  await expect(page.getByTestId('warning-map-count')).toHaveCount(0);
  await expect(details.getByRole('article')).toHaveCount(1);
  await page
    .getByRole('checkbox', { name: 'Warning areas', exact: true })
    .check();
  await page
    .getByRole('button', { name: '60s · Watch and Act', exact: true })
    .click();
  await expect(page.locator('.condition-box strong')).toHaveText('Degraded');
  await expect(page.locator('.reason')).toHaveCount(2);
  await page
    .getByRole('button', { name: '150s · Cancelled', exact: true })
    .click();
  await expect(details.getByText('cancelled', { exact: true })).toBeVisible();
  await expect(page.locator('.reason')).toHaveCount(1);
  await expect(page.getByTestId('warning-map-count')).toHaveText(
    '0 active warning areas',
  );
  await page
    .getByRole('button', { name: '180s · Emergency Warning', exact: true })
    .click();
  await expect(page.locator('.reason')).toHaveCount(1);
  await expect(page.locator('.reason')).toContainText('Emergency Warning');
  await expect(page.getByTestId('warning-map-count')).toHaveText(
    '1 active warning areas',
  );
  await mkdir('../../.local/city02', { recursive: true });
  await page.screenshot({
    path: '../../.local/city02/weather-desktop.png',
    fullPage: true,
  });
  await page
    .getByRole('button', {
      name: '240s · Expired, coverage stale',
      exact: true,
    })
    .click();
  await expect(page.locator('.condition-box strong')).toHaveText('Unknown');
  await expect(details.locator('.warning-heading').first()).toContainText(
    'stale',
  );
  await expect(details.getByText('expired', { exact: true })).toBeVisible();
  await page
    .getByRole('button', { name: '270s · Coverage restored', exact: true })
    .click();
  await expect(page.locator('.condition-box strong')).toHaveText('Normal');
  await page
    .getByRole('button', { name: '330s · Incomplete coverage', exact: true })
    .click();
  await expect(page.locator('.condition-box strong')).toHaveText('Unknown');
  await expect(details.getByText(/Area applicability unknown/)).toBeVisible();
  expect(errors).toEqual([]);
  expect(external).toEqual([]);
});

test('outage keeps received warning and attribution without leaking cancellation', async ({
  page,
}) => {
  await page.goto('/?scenario=weather');
  await page
    .getByRole('group', { name: 'Scenario', exact: true })
    .getByRole('button', { name: 'Weather outage', exact: true })
    .click();
  await page
    .getByRole('button', { name: '180s · Emergency Warning', exact: true })
    .click();
  const details = page.getByRole('region', { name: 'Weather details' });
  await expect(page.locator('.condition-box strong')).toHaveText('Degraded');
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
  await page
    .getByRole('button', {
      name: '240s · Expired, coverage stale',
      exact: true,
    })
    .click();
  await expect(page.locator('.condition-box strong')).toHaveText('Unknown');
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
  await page
    .getByRole('group', { name: 'Scenario', exact: true })
    .getByRole('button', { name: 'Weather warnings', exact: true })
    .click();
  await page
    .getByRole('button', { name: '270s · Coverage restored', exact: true })
    .click();
  await expect(page.locator('.condition-box strong')).toHaveText('Normal');
  await page.getByRole('button', { name: '30s · Advice', exact: true }).click();
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
  test(`weather is visible on arrival without scrolling at ${viewport.width}px`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    await page.goto('/?scenario=weather');
    const scenarios = page.getByRole('group', {
      name: 'Scenario',
      exact: true,
    });
    await expect(
      scenarios.getByRole('button', { name: 'Weather warnings', exact: true }),
    ).toHaveAttribute('aria-pressed', 'true');
    await expect(page.getByRole('combobox')).toHaveCount(0);
    const summary = page.getByRole('region', { name: 'Weather summary' });
    await expect(summary).toContainText('18 °C');
    const bounds = await summary.boundingBox();
    expect(bounds!.y).toBeGreaterThanOrEqual(0);
    expect(bounds!.y + bounds!.height).toBeLessThan(viewport.height);
    expect(await page.evaluate(() => window.scrollY)).toBe(0);
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(viewport.width);
    if (viewport.width > 760) {
      const map = await page.locator('.map-card').boundingBox();
      const warnings = await page
        .getByRole('region', { name: 'Weather details' })
        .boundingBox();
      expect(warnings!.y - (map!.y + map!.height)).toBeLessThanOrEqual(16);
    }
    await mkdir('../../.local/city02', { recursive: true });
    await page.screenshot({
      path: `../../.local/city02/arrival-${viewport.width}.png`,
      fullPage: true,
    });
  });
}

test('scenario buttons support keyboard selection and preserve the chosen clock', async ({
  page,
}) => {
  await page.goto('/?scenario=weather');
  await page
    .getByRole('button', { name: '60s · Watch and Act', exact: true })
    .click();
  const scenarios = page.getByRole('group', { name: 'Scenario', exact: true });
  const tram = scenarios.getByRole('button', {
    name: 'Tram journey',
    exact: true,
  });
  await tram.focus();
  await tram.press('Enter');
  await expect(tram).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByTestId('clock')).toHaveText('11:01:00');
  await expect(
    page.getByRole('region', { name: 'Weather summary' }),
  ).toContainText('not included');
  await page.getByRole('button', { name: 'Show weather', exact: true }).click();
  await expect(
    scenarios.getByRole('button', { name: 'Weather warnings', exact: true }),
  ).toHaveAttribute('aria-pressed', 'true');
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
    await expect(
      summary.getByRole('button', { name: 'Show weather' }),
    ).toHaveCount(0);
    await expect(
      page.getByRole('region', { name: 'Weather details' }),
    ).toBeVisible();
  });
}

test('scenario navigation updates shareable URLs and supports browser history', async ({
  page,
}) => {
  await page.goto('/?scenario=weather&example=keep#demo');
  await expect(
    page.getByRole('region', { name: 'Weather summary' }),
  ).toContainText('18 °C');
  const scenarios = page.getByRole('group', { name: 'Scenario', exact: true });
  await scenarios
    .getByRole('button', { name: 'Tram journey', exact: true })
    .click();
  await expect(page).toHaveURL(/scenario=journey&example=keep#demo$/);
  await expect(
    page.getByRole('region', { name: 'Weather summary' }),
  ).toContainText('transport scenario');
  await page.goBack();
  await expect(
    scenarios.getByRole('button', { name: 'Weather warnings', exact: true }),
  ).toHaveAttribute('aria-pressed', 'true');
  await expect(
    page.getByRole('region', { name: 'Weather summary' }),
  ).toContainText('18 °C');
  await page.goForward();
  await expect(
    scenarios.getByRole('button', { name: 'Tram journey', exact: true }),
  ).toHaveAttribute('aria-pressed', 'true');
  await page.reload();
  await expect(
    scenarios.getByRole('button', { name: 'Tram journey', exact: true }),
  ).toHaveAttribute('aria-pressed', 'true');
  await expect(
    page.getByRole('region', { name: 'Weather summary' }),
  ).toContainText('transport scenario');
  await page.getByRole('button', { name: 'Show weather', exact: true }).click();
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
    bounds!.x + bounds!.width / 2,
    bounds!.y + bounds!.height / 2,
  );
  await page.mouse.down();
  await page.mouse.move(
    bounds!.x + bounds!.width / 2 + 30,
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
  await page.getByRole('button', { name: 'Tram journey', exact: true }).click();
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
  await page.getByRole('button', { name: 'Tram journey', exact: true }).click();
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
