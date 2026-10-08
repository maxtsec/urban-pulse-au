import { expect, test } from '@playwright/test';
test('Pages subpath works without API, credentials, tiles or external asset requests', async ({
  page,
}) => {
  const requests: string[] = [],
    errors: string[] = [];
  page.on('request', (r) => {
    if (
      /^https?:/.test(r.url()) &&
      (!r.url().startsWith('http://127.0.0.1:5182/urban-pulse-au/') ||
        r.url().includes('/api/'))
    )
      requests.push(r.url());
  });
  page.on('pageerror', (e) => errors.push(e.message));
  await page.goto('./');
  await expect(
    page.getByRole('heading', { name: 'CBD + Southbank', level: 1 }),
  ).toBeVisible();
  await expect(
    page.locator('meta[http-equiv="Content-Security-Policy"]'),
  ).toHaveAttribute('content', /connect-src 'self'/);
  await page.getByRole('tab', { name: 'Trams', exact: true }).click();
  await expect(page.getByRole('tabpanel')).toContainText(
    'Schedule simulation, not live',
  );
  expect(
    await page.locator('.information-content .detail-row').count(),
  ).toBeGreaterThan(20);
  await page.getByRole('button', { name: 'Sources & attribution' }).click();
  await expect(page.getByRole('dialog')).toContainText('Vicmap Hydro');
  await expect(
    page
      .getByRole('dialog')
      .getByRole('link', { name: 'CC BY 4.0', exact: true }),
  ).toHaveCount(6);
  await page.getByRole('button', { name: 'Close sources' }).click();
  await page.getByRole('button', { name: '3D', exact: true }).click();
  await expect(page.getByTestId('map')).toHaveAttribute(
    'data-models',
    'ready',
    { timeout: 15000 },
  );
  await page.screenshot({ path: 'test-results/pages-sample.png' });
  expect(errors).toEqual([]);
  expect(requests).toEqual([]);
});
test('corrupt schedule asset fails visibly rather than displaying fabricated fallback data', async ({
  page,
}) => {
  await page.route('**/city-*.json', (r) =>
    r.fulfill({ status: 200, body: '{}' }),
  );
  await page.goto('./');
  await expect(
    page.getByRole('heading', { name: 'City sample unavailable' }),
  ).toBeVisible();
  await expect(page.getByTestId('map')).toHaveCount(0);
});
