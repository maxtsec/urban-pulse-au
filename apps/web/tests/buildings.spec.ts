import { expect, test } from '@playwright/test';
import { closeLayers, condition, layer, openTab } from './helpers';

test('3D buildings load on demand, preserve API state and keyboard selection, and toggle cleanly', async ({
  page,
}, info) => {
  const errors: string[] = [];
  const external: string[] = [];
  const requests: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('request', (request) => {
    const url = request.url();
    requests.push(url);
    if (/^https?:/.test(url) && new URL(url).hostname !== '127.0.0.1')
      external.push(url);
  });
  await page.goto('/?scenario=city');
  const map = page.getByTestId('map');
  await expect(
    page.getByRole('button', { name: 'Select Tram 01 on map', exact: true }),
  ).toBeVisible();
  await expect(map).toHaveAttribute('data-view', '2d');
  expect(requests.filter((url) => url.includes('southbank-buildings'))).toEqual(
    [],
  );
  const before = await condition(page).innerText();
  const apiCount = requests.filter((url) => url.includes('/api/')).length;
  const canvas = await map.locator('canvas').elementHandle();
  await page.getByRole('button', { name: '3D view', exact: true }).click();
  await expect(map).toHaveAttribute('data-buildings', 'ready');
  await expect(
    page.getByRole('button', { name: '3D view', exact: true }),
  ).toHaveAttribute('aria-pressed', 'true');
  const buildings = await layer(page, 'Buildings (historical)');
  await buildings.uncheck();
  await expect(map).toHaveAttribute('data-buildings', 'hidden');
  await buildings.check();
  await expect(map).toHaveAttribute('data-buildings', 'ready');
  await closeLayers(page);
  await openTab(page, 'Trams');
  const list = page.getByRole('button', {
    name: 'Select Tram 01 in list',
    exact: true,
  });
  await list.focus();
  await page.keyboard.press('Enter');
  await expect(
    page.getByRole('button', { name: 'Select Tram 01 on map', exact: true }),
  ).toHaveAttribute('aria-pressed', 'true');
  await expect(condition(page)).toHaveText(before);
  expect(requests.filter((url) => url.includes('/api/')).length).toBe(apiCount);
  await page.locator('.map-credit summary').click();
  await expect(page.locator('.map-credit')).toContainText('captured 2018–2023');
  await expect(page.locator('.map-credit')).toContainText('CC BY 4.0');
  await page.screenshot({
    path: info.outputPath('southbank-3d.png'),
    fullPage: true,
  });
  await page.getByRole('button', { name: '3D view', exact: true }).click();
  await expect(map).toHaveAttribute('data-buildings', 'hidden');
  expect(await canvas!.evaluate((element) => element.isConnected)).toBe(true);
  expect(
    requests.filter(
      (url) => url.includes('southbank-buildings') && url.endsWith('.geojson'),
    ),
  ).toHaveLength(1);
  expect(errors).toEqual([]);
  expect(external).toEqual([]);
});

test('missing building asset leaves city details usable and can retry', async ({
  page,
}) => {
  await page.route('**/southbank-buildings-*.geojson', (route) =>
    route.abort(),
  );
  await page.goto('/?scenario=city');
  await expect(
    page.getByRole('button', { name: 'Select Tram 01 on map', exact: true }),
  ).toBeVisible();
  await page.getByRole('button', { name: '3D view', exact: true }).click();
  await expect(page.getByTestId('map')).toHaveAttribute(
    'data-buildings',
    'unavailable',
  );
  await expect(
    page.getByText('Buildings unavailable.', { exact: false }),
  ).toBeVisible();
  await openTab(page, 'Trams');
  await expect(
    page.getByRole('button', { name: 'Select Tram 01 in list', exact: true }),
  ).toBeVisible();
  await page.unroute('**/southbank-buildings-*.geojson');
  await page.getByRole('button', { name: '3D view', exact: true }).click();
  await page.getByRole('button', { name: '3D view', exact: true }).click();
  await expect(page.getByTestId('map')).toHaveAttribute(
    'data-buildings',
    'ready',
  );
});

test('mobile reduced-motion view retains visible controls and local building context', async ({
  page,
}, info) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/?scenario=city');
  await expect(
    page.getByRole('button', { name: 'Select Tram 01 on map', exact: true }),
  ).toBeVisible();
  await page.getByRole('button', { name: '3D view', exact: true }).click();
  await expect(page.getByTestId('map')).toHaveAttribute(
    'data-buildings',
    'ready',
  );
  await expect(
    page.getByRole('button', { name: 'Pause', exact: true }),
  ).toHaveCount(0);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: info.outputPath('southbank-3d-mobile.png'),
    fullPage: true,
  });
});
