import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { openTab } from './helpers';

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
  await page.goto('/?scenario=city');
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

test('WebGL context loss shows the fallback and preserves the accessible city list', async ({
  page,
}) => {
  await page.goto('/?scenario=city');
  await expect(
    page.getByRole('button', { name: 'Select Tram 01 on map', exact: true }),
  ).toBeVisible();
  await page.getByRole('button', { name: '3D view', exact: true }).click();
  await expect(page.getByTestId('map')).toHaveAttribute(
    'data-buildings',
    'ready',
  );
  await page
    .getByTestId('map')
    .locator('canvas')
    .evaluate((canvas: HTMLCanvasElement) => {
      const extension = canvas
        .getContext('webgl2')!
        .getExtension('WEBGL_lose_context');
      if (!extension)
        throw new Error('Test browser does not support context loss');
      extension.loseContext();
    });
  await expect(
    page.getByText('Map unavailable.', { exact: false }),
  ).toBeVisible();
  await openTab(page, 'Trams');
  const list = page.getByRole('button', {
    name: 'Select Tram 01 in list',
    exact: true,
  });
  await list.focus();
  await page.keyboard.press('Enter');
  await expect(list).toHaveAttribute('aria-pressed', 'true');
});
