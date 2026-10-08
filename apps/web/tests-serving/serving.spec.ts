import { expect, test } from '@playwright/test';

function expectSecurityHeaders(response: {
  headers(): Record<string, string>;
}) {
  const headers = response.headers();
  expect(headers['server']).toBeUndefined();
  expect(headers['x-content-type-options']).toBe('nosniff');
  expect(headers['x-frame-options']).toBe('DENY');
  expect(headers['referrer-policy']).toBe('strict-origin-when-cross-origin');
  expect(headers['strict-transport-security']).toBe('max-age=31536000');
  const policy = headers['content-security-policy'];
  expect(policy).toContain("default-src 'self'");
  expect(policy).toContain("script-src 'self'");
  expect(policy).toContain("worker-src 'self'");
  expect(policy).toContain("frame-ancestors 'none'");
  expect(policy).not.toContain("'unsafe-eval'");
}

const area = '/api/v1/areas/au-vic-melbourne-clue-southbank';

test('compiled schedule sample reloads from a nested URL without a dev runtime', async ({
  page,
}) => {
  await page.addInitScript(() => {
    const violations: string[] = [];
    document.addEventListener('securitypolicyviolation', (event) => {
      violations.push(`${event.effectiveDirective}: ${event.blockedURI}`);
    });
    Object.defineProperty(window, 'servingCspViolations', {
      value: violations,
    });
  });
  const requests: string[] = [];
  page.on('request', (request) => requests.push(request.url()));
  await page.goto('/city/southbank?scenario=city');
  await expect(
    page.getByRole('heading', { name: 'CBD + Southbank', level: 1 }),
  ).toBeVisible();
  await expect(
    page.getByRole('button', { name: /^Select Route .* on map$/ }).first(),
  ).toBeVisible();
  await expect(
    page.getByRole('heading', { name: 'No known impacts' }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () =>
        (window as unknown as { servingCspViolations: string[] })
          .servingCspViolations,
    ),
  ).toEqual([]);
  await page.reload();
  await expect(page.getByRole('tab', { name: 'Area health' })).toBeVisible();
  expect(
    await page.evaluate(
      () =>
        (window as unknown as { servingCspViolations: string[] })
          .servingCspViolations,
    ),
  ).toEqual([]);
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
  expectSecurityHeaders(index);
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
    expectSecurityHeaders(response);
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
    expectSecurityHeaders(response);
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
  expectSecurityHeaders(ready);
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
    expectSecurityHeaders(response);
    expect(response.headers()['content-type']).toContain('application/json');
    expect(await response.json()).toHaveProperty('detail');
  }
});

test('CSP blocks inline scripts without disrupting the compiled map', async ({
  page,
}) => {
  await page.goto('/?scenario=city');
  await expect(
    page.getByRole('button', { name: /^Select Route .* on map$/ }).first(),
  ).toBeVisible();
  const blocked = page.waitForEvent('console', {
    predicate: (message) => message.text().includes('script-src'),
  });
  const executed = await page.evaluate(() => {
    const script = document.createElement('script');
    script.textContent = 'window.servingInlineScriptExecuted = true';
    document.head.append(script);
    return (window as unknown as { servingInlineScriptExecuted?: boolean })
      .servingInlineScriptExecuted;
  });
  await blocked;
  expect(executed).toBeUndefined();
});

test('an external page cannot frame the city', async ({
  page,
  context,
  baseURL,
}) => {
  const parent = 'http://localhost:38081';
  const framed = `${baseURL}/?scenario=city`;
  // Let the request reach ingress instead of failing Chromium's loopback checks.
  await context.grantPermissions(['local-network-access'], { origin: parent });
  await page.route(`${parent}/**`, (route) =>
    route.fulfill({
      contentType: 'text/html',
      headers: {
        'Permissions-Policy':
          'local-network-access=*, local-network=*, loopback-network=*',
      },
      body: `<iframe src="${framed}" allow="local-network-access; local-network; loopback-network"></iframe>`,
    }),
  );
  const blocked = page.waitForEvent('requestfailed', {
    predicate: (request) => request.url() === framed,
  });
  await page.goto(parent);
  expect((await blocked).failure()?.errorText).toContain(
    'ERR_BLOCKED_BY_RESPONSE',
  );
  await expect(
    page
      .frameLocator('iframe')
      .getByRole('heading', { name: 'CBD + Southbank', level: 1 }),
  ).toHaveCount(0);
});

test('cross-origin navigation sends only the origin as Referer', async ({
  page,
  baseURL,
}) => {
  await page.route('http://external.test/**', (route) =>
    route.fulfill({
      contentType: 'text/html',
      body: '<p>External destination</p>',
    }),
  );
  await page.goto('/?scenario=city');
  await page.evaluate(() => {
    const link = document.createElement('a');
    link.href = 'http://external.test/shared';
    link.textContent = 'External destination';
    document.body.append(link);
  });
  const outgoing = page.waitForRequest('http://external.test/shared');
  await page.getByRole('link', { name: 'External destination' }).click();
  expect((await outgoing).headers()['referer']).toBe(
    `${new URL(baseURL!).origin}/`,
  );
});
