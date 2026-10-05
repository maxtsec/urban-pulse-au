import { expect, test } from '@playwright/test';

const area = '/api/v1/areas/au-vic-melbourne-clue-southbank';

test('compiled city reloads from a nested URL with three domains and no dev runtime', async ({
  page,
}) => {
  const requests: string[] = [];
  page.on('request', (request) => requests.push(request.url()));
  await page.goto('/city/southbank?scenario=city');
  await expect(
    page.getByRole('heading', { name: 'Southbank', level: 1 }),
  ).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'Select Tram 01 on map', exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole('region', { name: 'Weather summary' }),
  ).toContainText('18 °C');
  await expect(page.getByTestId('planning-map-count')).toHaveText(
    '3 developments',
  );
  await page.reload();
  await expect(
    page.getByRole('button', { name: 'City overview', exact: true }),
  ).toHaveAttribute('aria-pressed', 'true');
  await expect(
    page.getByRole('region', { name: 'Weather summary' }),
  ).toContainText('18 °C');
  await expect(page.getByTestId('planning-map-count')).toHaveText(
    '3 developments',
  );
  expect(
    requests.some((url) => /\/@vite\/|\/src\/|\/node_modules\//.test(url)),
  ).toBe(false);
  expect(
    requests
      .filter((url) => /^https?:/.test(url))
      .every((url) => new URL(url).origin === new URL(page.url()).origin),
  ).toBe(true);
});

test('HTML revalidates, compiled assets cache, missing assets and private paths do not return the SPA', async ({
  request,
}) => {
  const index = await request.get('/');
  expect(index.status()).toBe(200);
  expect(index.headers()['cache-control']).toBe('no-cache');
  const html = await index.text();
  expect(html).not.toMatch(/\/@vite\/|\/src\/main/);
  const assets = [...html.matchAll(/(?:src|href)="(\/assets\/[^"]+)"/g)].map(
    (match) => match[1],
  );
  expect(assets.length).toBeGreaterThan(0);
  for (const asset of assets) {
    const response = await request.get(asset);
    expect(response.status()).toBe(200);
    expect(response.headers()['cache-control']).toContain('immutable');
    expect(response.headers()['x-content-type-options']).toBe('nosniff');
    expect(response.headers()['content-type']).not.toContain('text/html');
  }
  for (const path of [
    '/assets/missing.js',
    '/assets/missing.css',
    '/.env',
    '/.git/config',
    '/src/main.tsx',
    '/@vite/client',
    '/node_modules/vite/package.json',
    '/Caddyfile',
    '/package.json',
  ]) {
    const response = await request.get(path);
    expect(response.status(), path).toBe(404);
    expect(await response.text()).not.toContain('<div id="root">');
    expect(response.headers()['cache-control'] ?? '').not.toContain(
      'immutable',
    );
  }
});

test('API query strings, errors and health retain backend semantics through the serving origin', async ({
  request,
}) => {
  const ready = await request.get('/health/ready');
  expect(ready.status()).toBe(200);
  expect(await ready.json()).toEqual({
    status: 'ok',
    postgis: 'ok',
    redis: 'disabled',
    mode: 'fixture',
  });
  expect(ready.headers()['cache-control']).toBe('no-store');
  const early = await request.get(`${area}?scenario=city&seconds=0`);
  const later = await request.get(`${area}?scenario=city&seconds=180`);
  expect(early.status()).toBe(200);
  expect(later.status()).toBe(200);
  expect(await later.json()).not.toEqual(await early.json());
  expect(later.headers()['cache-control']).toBe('no-store');
  for (const [path, status] of [
    [`${area}?scenario=invalid`, 422],
    ['/api/v1/missing', 404],
    ['/health/missing', 404],
    ['/api', 404],
    ['/health', 404],
  ] as const) {
    const response = await request.get(path);
    expect(response.status()).toBe(status);
    expect(response.headers()['content-type']).toContain('application/json');
    expect(await response.json()).toHaveProperty('detail');
  }
});
