import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { moment, openTab } from './helpers';

test('3D renders under the deployed Content Security Policy without relaxing it', async ({
  page,
}) => {
  const caddy = readFileSync(new URL('../Caddyfile', import.meta.url), 'utf8');
  const policy = caddy.match(/Content-Security-Policy "([^"]+)"/)![1];
  const errors: string[] = [];
  page.on('console', (message) => {
    if (/Content Security Policy|violates.*directive/i.test(message.text()))
      errors.push(message.text());
  });
  page.on('pageerror', (error) => errors.push(error.message));
  await page.route('**/*', async (route) => {
    if (route.request().resourceType() !== 'document') return route.continue();
    const response = await route.fetch();
    await route.fulfill({
      response,
      headers: { ...response.headers(), 'content-security-policy': policy },
    });
  });
  await page.goto('/tests/scenario.html?scenario=city');
  await expect(
    page.getByRole('button', { name: 'Select Tram 01 on map', exact: true }),
  ).toBeVisible();
  await page.getByRole('button', { name: '3D view', exact: true }).click();
  await expect(page.getByTestId('map')).toHaveAttribute(
    'data-buildings',
    'ready',
  );
  await page.mouse.move(550, 500);
  await page.getByRole('button', { name: '3D view', exact: true }).click();
  expect(errors).toEqual([]);
});

test('WebGL loss hides stale markers and restoration renders the latest clock and selection', async ({
  page,
}) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/tests/scenario.html?scenario=city');
  const marker = page.getByRole('button', {
    name: 'Select Tram 01 on map',
    exact: true,
  });
  await expect(marker).toBeVisible();
  await page.getByRole('button', { name: '3D view', exact: true }).click();
  await expect(page.getByTestId('map')).toHaveAttribute(
    'data-buildings',
    'ready',
  );
  // A rotated camera must also survive GPU recovery.
  const canvas = page.getByTestId('map').locator('canvas');
  const box = (await canvas.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down({ button: 'right' });
  await page.mouse.move(box.x + box.width / 2 + 45, box.y + box.height / 2, {
    steps: 5,
  });
  await page.mouse.up({ button: 'right' });
  await moment(page, '30s · Advice').click();
  await expect(page.getByTestId('clock')).toHaveText('11:00:30');
  const expected = await marker.boundingBox();
  await page.getByRole('button', { name: 'Reset', exact: true }).click();
  await expect(page.getByTestId('clock')).toHaveText('11:00:00');

  for (let attempt = 0; attempt < 2; attempt++) {
    const extension = await page
      .getByTestId('map')
      .locator('canvas')
      .evaluateHandle((canvas: HTMLCanvasElement) => {
        const extension = canvas
          .getContext('webgl2')!
          .getExtension('WEBGL_lose_context');
        if (!extension)
          throw new Error('Test browser does not support context loss');
        return extension;
      });
    await extension.evaluate((extension) => extension.loseContext());
    await expect(
      page.getByText('Map unavailable.', { exact: false }),
    ).toBeVisible();
    await expect(page.locator('.maplibregl-marker')).toHaveCount(0);
    await moment(page, '30s · Advice').click();
    await expect(page.getByTestId('clock')).toHaveText('11:00:30');
    await openTab(page, 'Trams');
    const list = page.getByRole('button', {
      name: 'Select Tram 01 in list',
      exact: true,
    });
    await list.focus();
    await page.keyboard.press('Enter');
    await expect(list).toHaveAttribute('aria-pressed', 'true');
    await extension.evaluate((extension) => extension.restoreContext());
    await expect(
      page.getByText('Map unavailable.', { exact: false }),
    ).toHaveCount(0);
    await expect(page.getByTestId('map')).toHaveAttribute(
      'data-buildings',
      'ready',
    );
    await expect(marker).toBeVisible();
    await expect(marker).toHaveAttribute('aria-pressed', 'true');
    const restored = (await marker.boundingBox())!;
    expect(Math.abs(restored.x - expected!.x)).toBeLessThan(1);
    expect(Math.abs(restored.y - expected!.y)).toBeLessThan(1);
    await extension.dispose();
  }
  await page.getByRole('button', { name: 'Reset', exact: true }).click();
  await expect(page.getByTestId('clock')).toHaveText('11:00:00');
  await expect
    .poll(async () => Math.abs((await marker.boundingBox())!.x - expected!.x))
    .toBeGreaterThan(1);
  expect(errors).toEqual([]);
});
