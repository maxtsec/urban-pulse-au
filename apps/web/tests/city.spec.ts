import { expect, test } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import {
  chooseScenario,
  closeLayers,
  condition,
  detailsTab,
  layer,
  moment,
  openTab,
} from './helpers';

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
  await page.goto('/?scenario=journey');
  await expect(
    page.getByRole('heading', { name: 'Southbank', level: 1 }),
  ).toBeVisible();
  await expect(page.getByText('SYNTHETIC DEMO · NO LIVE DATA')).toBeVisible();
  const marker = page.getByRole('button', {
    name: 'Select Tram 01 on map',
    exact: true,
  });
  await expect(marker).toBeVisible();
  await expect(marker.locator('img')).toBeVisible();
  expect(
    await marker
      .locator('img')
      .evaluate(
        (image: HTMLImageElement) => image.complete && image.naturalWidth > 0,
      ),
  ).toBe(true);
  const tracks = await layer(page, 'Tracks (illustrative)');
  await expect(page.getByTestId('tracks-note')).toContainText(
    'Illustrative tracks',
  );
  await tracks.uncheck();
  await expect(page.getByTestId('tracks-note')).toHaveCount(0);
  await expect(marker).toBeVisible();
  await tracks.check();
  await closeLayers(page);
  const before = await marker.boundingBox();
  await openTab(page, 'Trams');
  const list = page.getByRole('button', {
    name: 'Select Tram 01 in list',
    exact: true,
  });
  await list.focus();
  await page.keyboard.press('Enter');
  await expect(marker).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByText('Tram 01 selected')).toBeVisible();
  await moment(page, '30s · Position update').click();
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
  await page.getByRole('button', { name: 'Clear selection' }).click();
  await expect(page.getByText('Tram 01 selected')).toHaveCount(0);
  await expect(list).toHaveAttribute('aria-pressed', 'false');
  await (await layer(page, 'Tram positions')).uncheck();
  await expect(marker).toHaveCount(0);
  await expect(list).toBeVisible();
  await (await layer(page, 'Tram positions')).check();
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

test('map-first layout keeps the map dominant with data on the map', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/');
  await expect(page.locator('.maplibregl-canvas')).toBeVisible();
  const map = (await page.locator('.map-area').boundingBox())!;
  expect(map.width).toBe(1440);
  expect(map.height).toBeGreaterThan(820);
  for (const overlay of [
    page.getByTestId('condition'),
    page.getByRole('region', { name: 'Weather summary' }),
    page.getByRole('region', { name: 'Scenario playback' }),
  ]) {
    const box = (await overlay.boundingBox())!;
    expect(box.y).toBeGreaterThanOrEqual(map.y);
    expect(box.y + box.height).toBeLessThanOrEqual(map.y + map.height);
  }
  expect(
    await page.evaluate(
      () => document.documentElement.scrollHeight <= window.innerHeight,
    ),
  ).toBe(true);
  await page.getByRole('button', { name: 'Hide details' }).click();
  await expect(
    page.getByRole('complementary', { name: 'City details' }),
  ).toHaveCount(0);
  await page.getByRole('button', { name: 'Show details' }).click();
  await expect(
    page.getByRole('complementary', { name: 'City details' }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Hide details' }).click();
  await page.getByTestId('condition').click();
  await expect(detailsTab(page, 'Overview')).toHaveAttribute(
    'aria-selected',
    'true',
  );
  await mkdir('../../.local/city01', { recursive: true });
  await page.screenshot({ path: '../../.local/city01/map-first.png' });
});

test('playback keeps the camera and page stationary', async ({ page }) => {
  await page.goto('/');
  const site = page.locator('.development-marker').first();
  await expect(site).toBeVisible();
  const before = await site.boundingBox();
  await page.getByRole('button', { name: 'Play scenario' }).click();
  await expect(page.getByTestId('clock')).toHaveText('11:00:45', {
    timeout: 10_000,
  });
  await page.getByRole('button', { name: 'Pause', exact: true }).click();
  expect(await site.boundingBox()).toEqual(before);
  expect(await page.evaluate(() => window.scrollY)).toBe(0);
});

test('visible map labels do not overlap markers or each other', async ({
  page,
}) => {
  await page.goto('/');
  await expect(page.locator('.development-marker')).toHaveCount(3);
  for (const seconds of ['0', '150', '300']) {
    await page.getByLabel('Scenario time', { exact: true }).fill(seconds);
    // Placement runs on the next animation frame after marker updates.
    await page.waitForTimeout(250);
    const boxes = await page.evaluate(() => {
      const box = (node: Element) => node.getBoundingClientRect().toJSON();
      return {
        labels: [...document.querySelectorAll('.tram-marker')]
          .filter((node) => !node.classList.contains('label-collapsed'))
          .map((node) => box(node.querySelector('.marker-label')!)),
        icons: [
          ...document.querySelectorAll('.tram-marker img, .development-marker'),
        ].map(box),
      };
    });
    type Rect = { x: number; y: number; width: number; height: number };
    const overlap = (a: Rect, b: Rect) =>
      a.x < b.x + b.width &&
      a.x + a.width > b.x &&
      a.y < b.y + b.height &&
      a.y + a.height > b.y;
    expect(boxes.labels.length).toBeGreaterThan(0);
    boxes.labels.forEach((label, index) => {
      boxes.icons.forEach((icon) => expect(overlap(label, icon)).toBe(false));
      boxes.labels
        .slice(index + 1)
        .forEach((other) => expect(overlap(label, other)).toBe(false));
    });
  }
});

test('playback, stale/expired positions and missing domains remain truthful', async ({
  page,
}) => {
  await page.goto('/?scenario=journey');
  await expect(
    page.getByRole('button', { name: 'Select Tram 01 on map' }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Play scenario' }).click();
  await expect(page.getByTestId('clock')).toHaveText('11:00:15');
  await page.getByRole('button', { name: 'Pause', exact: true }).click();
  await moment(page, '150s · Stale position').click();
  await expect(page.getByTestId('clock')).toHaveText('11:02:30');
  await expect(
    page.getByRole('button', { name: 'Select Tram 01 on map' }),
  ).toHaveClass(/stale/);
  await expect(condition(page)).toHaveText('Degraded');
  await expect(page.getByText('Warning data not connected')).toBeVisible();
  await expect(page.getByText('Development data not connected')).toBeVisible();
  await moment(page, '330s · Last known only').click();
  await expect(page.getByTestId('clock')).toHaveText('11:05:30');
  await expect(
    page.getByRole('button', { name: 'Select Tram 01 on map' }),
  ).toHaveCount(0);
  await openTab(page, 'Trams');
  await expect(
    page.getByRole('button', { name: 'Select Tram 01 in list' }),
  ).toContainText('last known');
  await expect(condition(page)).toHaveText('Unknown');
  await expect(
    page.getByRole('button', { name: 'Select Tram 03 in list' }),
  ).toContainText('Observation time unknown');
  await page.getByRole('button', { name: 'Reset', exact: true }).click();
  await expect(page.getByTestId('clock')).toHaveText('11:00:00');
});

test('empty, outage and error recovery are distinct', async ({ page }) => {
  await page.goto('/?scenario=journey');
  await chooseScenario(page, 'Empty transport');
  await openTab(page, 'Trams');
  await expect(
    page.getByText('No tram observations in this fixture view.'),
  ).toBeVisible();
  await expect(condition(page)).toHaveText('Unknown');
  await chooseScenario(page, 'Transport outage');
  await moment(page, '150s · Stale position').click();
  await openTab(page, 'Overview');
  await expect(page.getByText('Source unavailable · fixture')).toBeVisible();
  await expect(condition(page)).toHaveText('Degraded');
  await page.route('**/api/v1/areas/*?*', (route) =>
    route.fulfill({ status: 503, body: '{}' }),
  );
  await page.getByRole('button', { name: 'Reset', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText(
    'City snapshot unavailable',
  );
  await page.unroute('**/api/v1/areas/*?*');
  await page.getByRole('button', { name: 'Try again' }).click();
  await expect(page.getByTestId('clock')).toHaveText('11:00:00');
  await expect(condition(page)).toHaveText('Unknown');
});

test('boundary failure preserves the accessible observations', async ({
  page,
}) => {
  await page.route('**/boundaries/*', (route) =>
    route.fulfill({ status: 503, body: '{}' }),
  );
  await page.goto('/?scenario=journey');
  await expect(page.getByRole('alert')).toContainText('Boundary unavailable');
  await openTab(page, 'Trams');
  await page.getByRole('button', { name: 'Select Tram 01 in list' }).click();
  await expect(page.getByText('Tram 01 selected')).toBeVisible();
});

test('mobile layout fits and keeps the area overview usable', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/?scenario=journey');
  await expect(
    page.getByRole('button', { name: 'Select Tram 01 on map' }),
  ).toBeVisible();
  await expect(condition(page)).toBeInViewport();
  await expect(
    page.getByRole('heading', { name: 'Area conditions', exact: true }),
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

test('service replay reveals only received facts and outage cannot resolve them', async ({
  page,
}) => {
  await page.goto('/?scenario=journey');
  await moment(page, '60s · Service interruption').click();
  await expect(condition(page)).toHaveText('Degraded');
  await expect(page.getByTestId('condition')).toContainText('1 active reason');
  await expect(
    page.getByText('Resolution not yet observed', { exact: false }),
  ).toBeVisible();
  await expect(page.locator('.reason')).not.toContainText('11:03');
  await chooseScenario(page, 'Transport outage');
  await moment(page, '330s · Last known only').click();
  await expect(page.getByTestId('clock')).toHaveText('11:05:30');
  await expect(condition(page)).toHaveText('Degraded');
  await expect(page.getByText('Source unavailable · fixture')).toBeVisible();
  await expect(
    page.getByText('Resolution not yet observed', { exact: false }),
  ).toBeVisible();
  await chooseScenario(page, 'Tram journey');
  await expect(condition(page)).toHaveText('Unknown');
  await expect(page.locator('.reason')).toHaveCount(0);
});

test('unknown explanation identifies every missing required input', async ({
  page,
}) => {
  await page.route('**/api/v1/areas/*?*', async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    data.assessment.coverage.find(
      (entry: { input_id: string }) => entry.input_id === 'transport_service',
    ).state = 'error';
    data.assessment.incomplete_inputs = [
      'transport_service',
      'weather_warnings',
    ];
    await route.fulfill({ response, json: data });
  });
  await page.goto('/?scenario=journey');
  await expect(condition(page)).toHaveText('Unknown');
  for (const text of [
    'Transport service unavailable',
    'Weather warnings coverage missing',
  ]) {
    await expect(page.locator('.condition-explanation')).toContainText(text);
    await expect(page.getByTestId('condition')).toContainText(text);
  }
});

test('playback, markers and slider respect the API clock limit', async ({
  page,
}) => {
  const requested: number[] = [];
  await page.route('**/api/v1/areas/*?*', async (route) => {
    requested.push(
      Number(new URL(route.request().url()).searchParams.get('seconds')),
    );
    const response = await route.fetch();
    const data = await response.json();
    data.clock.end_seconds = 75;
    await route.fulfill({ response, json: data });
  });
  await page.goto('/?scenario=journey');
  const slider = page.getByLabel('Scenario time', { exact: true });
  await expect(slider).toHaveAttribute('max', '75');
  // Moments after the API clock are not offered.
  await expect(moment(page, '150s · Stale position')).toHaveCount(0);
  await expect(moment(page, '330s · Last known only')).toHaveCount(0);
  await moment(page, '60s · Service interruption').click();
  await expect(page.getByTestId('clock')).toHaveText('11:01:00');
  await page.getByRole('button', { name: 'Play scenario' }).click();
  await expect(page.getByTestId('clock')).toHaveText('11:01:15');
  await expect(
    page.getByRole('button', { name: 'Play scenario' }),
  ).toBeVisible();
  const refreshedClock = (seconds: number) =>
    page.waitForResponse((response) => {
      const url = new URL(response.url());
      return (
        url.pathname.startsWith('/api/v1/areas/') &&
        url.searchParams.get('seconds') === String(seconds)
      );
    });
  // Reset can render cached data before its background refetch finishes.
  await Promise.all([
    refreshedClock(0),
    page.getByRole('button', { name: 'Reset', exact: true }).click(),
  ]);
  await expect(page.getByTestId('clock')).toHaveText('11:00:00');
  // The furthest reachable clock is the API maximum.
  await slider.focus();
  await Promise.all([refreshedClock(75), slider.press('End')]);
  await expect(page.getByTestId('clock')).toHaveText('11:01:15');
  // A cached clock can render while React Query refetches; finish the interceptor before teardown.
  await page.unrouteAll({ behavior: 'wait' });
  expect(Math.max(...requested)).toBe(75);
});

for (const state of ['current', 'stale', 'error', 'unsupported']) {
  test(`weather coverage renders the API state: ${state}`, async ({ page }) => {
    await page.route('**/api/v1/areas/*?*', async (route) => {
      const response = await route.fetch();
      const data = await response.json();
      data.assessment.coverage.find(
        (entry: { input_id: string }) => entry.input_id === 'weather_warnings',
      ).state = state;
      data.assessment.incomplete_inputs =
        state === 'current' ? [] : ['weather_warnings'];
      data.assessment.condition = state === 'current' ? 'normal' : 'unknown';
      await route.fulfill({ response, json: data });
    });
    await page.goto('/?scenario=journey');
    const weather = page.locator('.domain-row').filter({
      has: page.getByRole('heading', { name: 'Weather & hazards' }),
    });
    await expect(weather.locator('.status-pill')).toHaveText(state);
    await expect(weather).not.toContainText('Warning data not connected');
  });
}

test('slider keyboard movement requests 15-second increments', async ({
  page,
}) => {
  const requested: number[] = [];
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (
      url.pathname.startsWith('/api/v1/areas/') &&
      url.searchParams.has('seconds')
    )
      requested.push(Number(url.searchParams.get('seconds')));
  });
  await page.goto('/?scenario=journey');
  await expect(page.getByTestId('clock')).toHaveText('11:00:00');
  const slider = page.getByLabel('Scenario time', { exact: true });
  await expect(slider).toHaveAttribute('step', '15');
  await slider.focus();
  await slider.press('ArrowRight');
  await expect(page.getByTestId('clock')).toHaveText('11:00:15');
  expect(requested.filter((seconds) => seconds > 0)).toEqual([15]);
});

test('detail tabs support arrow-key navigation', async ({ page }) => {
  await page.goto('/');
  await detailsTab(page, 'Overview').focus();
  await page.keyboard.press('ArrowRight');
  await expect(detailsTab(page, 'Trams')).toBeFocused();
  await expect(detailsTab(page, 'Trams')).toHaveAttribute(
    'aria-selected',
    'true',
  );
  await expect(
    page.getByRole('region', { name: 'Tram observations' }),
  ).toBeVisible();
  await page.keyboard.press('ArrowLeft');
  await page.keyboard.press('ArrowLeft');
  await expect(detailsTab(page, 'Warnings')).toHaveAttribute(
    'aria-selected',
    'true',
  );
});

for (const width of [320, 390]) {
  for (const scenario of ['journey', 'city']) {
    test(`layers remain operable at ${width}px in ${scenario}`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height: 740 });
      await page.goto('/?scenario=' + scenario);
      await expect(page.getByTestId('clock')).toHaveText('11:00:00');
      const checkbox = await layer(page, 'Tram positions');
      await expect(checkbox).toBeInViewport();
      await checkbox.uncheck();
      await expect(page.locator('.tram-marker')).toHaveCount(0);
      await checkbox.check();
      await expect(page.locator('.tram-marker')).not.toHaveCount(0);
      if (scenario === 'city') {
        const warnings = page.getByRole('checkbox', {
          name: 'Warning areas',
          exact: true,
        });
        await expect(warnings).toBeInViewport();
        await warnings.uncheck();
        await expect(warnings).not.toBeChecked();
      }
      const rect = await page.locator('.layers-popover').boundingBox();
      expect(rect!.x).toBeGreaterThanOrEqual(0);
      expect(rect!.x + rect!.width).toBeLessThanOrEqual(width);
    });
  }
}
