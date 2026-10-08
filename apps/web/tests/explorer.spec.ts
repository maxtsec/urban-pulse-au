import { readFileSync } from 'node:fs';
import { expect, test } from '@playwright/test';

test('full day keeps evenly spaced two-hour controls, weather and accessible selection', async ({
  page,
}) => {
  const apis: string[] = [];
  page.on('request', (r) => {
    if (r.url().includes('/api/')) apis.push(r.url());
  });
  await page.goto('/');
  await expect(
    page.getByRole('heading', { name: 'CBD + Southbank', level: 1 }),
  ).toBeVisible();
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
  await page.getByRole('tab', { name: 'Weather', exact: true }).click();
  await expect(page.getByRole('tabpanel')).toContainText('rainy');
  await expect(
    page.getByRole('button', { name: '22:00 to 24:00' }),
  ).toBeDisabled();
  await page.getByRole('tab', { name: 'Trams', exact: true }).click();
  const row = page.locator('.information-content .detail-row').first();
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
  await page.goto('/');
  await page.getByRole('button', { name: '3D', exact: true }).click();
  await expect(page.getByTestId('map')).toHaveAttribute(
    'data-models',
    'ready',
    { timeout: 15000 },
  );
  await expect(
    page.getByRole('button', { name: /^Select Route .* on map$/ }),
  ).toHaveCount(0);
  await page.getByLabel('History time').fill(String(9 * 3600000));
  await expect(page.locator('.weather-atmosphere')).toHaveClass(/rainy/);
  await page.getByRole('button', { name: 'Layers', exact: true }).click();
  await page.getByRole('checkbox', { name: 'weather', exact: true }).uncheck();
  await expect(page.locator('.weather-atmosphere')).toHaveCount(0);
  await page.getByRole('button', { name: '2D', exact: true }).click();
  await expect(
    page.getByRole('button', { name: /^Select Route .* on map$/ }).first(),
  ).toBeVisible();
  expect(errors).toEqual([]);
  expect(external).toEqual([]);
});
test('history pause, seek, speed and simulated live work without affecting fixture API', async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await page.goto('/');
  await page.getByRole('button', { name: '08:00 to 10:00' }).click();
  await page
    .getByRole('combobox', { name: 'Playback speed' })
    .selectOption('300');
  await page.getByRole('button', { name: 'Play demo' }).click();
  await expect(page.getByTestId('day-clock')).not.toHaveText('08:00:00');
  await page.getByRole('button', { name: 'Pause demo' }).click();
  const stopped = await page.getByTestId('day-clock').innerText();
  await page.waitForTimeout(200);
  await expect(page.getByTestId('day-clock')).toHaveText(stopped);
  await page.getByRole('button', { name: 'Go live', exact: true }).click();
  await expect(page.locator('.player-context')).toHaveText(
    'Simulated live · 1×',
  );
  await expect(
    page.getByRole('combobox', { name: 'Playback speed' }),
  ).toBeDisabled();
  await page.getByRole('button', { name: 'Pause demo', exact: true }).click();
  await expect(
    page.getByRole('combobox', { name: 'Playback speed' }),
  ).toBeEnabled();
});
test('mobile opens with a compact static 2D summary and usable day controls', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await expect(page.getByTestId('map')).toHaveAttribute('data-view', '2d');
  await expect(
    page.getByRole('complementary', { name: 'Area information' }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.getByRole('button', { name: '06:00 to 08:00' }).click();
  await expect(page.getByTestId('day-clock')).toHaveText('06:00:00');
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
  await page.goto('/');
  await page.getByRole('button', { name: '3D', exact: true }).click();
  await expect(page.getByTestId('map')).toHaveAttribute(
    'data-models',
    'ready',
    { timeout: 15000 },
  );
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
    page.getByRole('button', { name: /^Select Route .* on map$/ }).first(),
  ).toBeVisible();
});
test('missing buildings do not prevent models and WebGL recovery uses the selected time', async ({
  page,
}) => {
  await page.route('**/buildings*.geojson', (route) =>
    route.fulfill({ status: 503, body: 'unavailable' }),
  );
  await page.goto('/');
  await page.getByRole('button', { name: '3D', exact: true }).click();
  await expect(page.getByTestId('map')).toHaveAttribute(
    'data-models',
    'ready',
    { timeout: 15000 },
  );
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
  await expect(page.getByTestId('map')).toHaveAttribute(
    'data-models',
    'ready',
    { timeout: 15000 },
  );
  await expect(page.getByTestId('day-clock')).toHaveText('09:00:00');
  await page.getByRole('button', { name: '2D', exact: true }).click();
  await expect(
    page.getByRole('button', { name: /^Select Route .* on map$/ }).first(),
  ).toBeVisible();
  await extension.dispose();
});

test('sole interface has a fixed health-first panel, keyboard tabs and unobstructed zoom controls', async ({
  page,
}) => {
  await page.goto('/?scenario=weather');
  await expect(
    page.getByRole('combobox', { name: 'Scenario', exact: true }),
  ).toHaveCount(0);
  await expect(page.getByRole('tab', { name: 'Area health' })).toHaveAttribute(
    'aria-selected',
    'true',
  );
  await expect(
    page.getByRole('heading', { name: 'Not assessed' }),
  ).toBeVisible();
  const panel = page.getByRole('complementary', { name: 'Area information' });
  const before = await panel.boundingBox();
  for (const tab of ['Weather', 'Trams', 'Works', 'Area health']) {
    await page.getByRole('tab', { name: tab, exact: true }).click();
    expect(await panel.boundingBox()).toEqual(before);
  }
  await page.getByRole('tab', { name: 'Area health' }).focus();
  await page.keyboard.press('ArrowRight');
  await expect(
    page.getByRole('tab', { name: 'Weather', exact: true }),
  ).toBeFocused();
  const zoom = page.getByRole('button', { name: 'Zoom in', exact: true });
  const bounds = await zoom.boundingBox();
  expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(before!.x);
  await zoom.click();
});

test('history never exposes future time or weather and go live follows the advancing edge', async ({
  page,
}) => {
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Go live' })).toHaveClass(
    /at-live/,
  );
  await page.getByRole('button', { name: '08:00 to 10:00' }).click();
  await page.getByRole('tab', { name: 'Weather', exact: true }).click();
  await expect(page.getByRole('tabpanel')).not.toContainText('09:00');
  await expect(
    page.getByRole('button', { name: '12:00 to 14:00' }),
  ).toBeDisabled();
  await page.waitForTimeout(1100);
  await page.getByRole('button', { name: 'Go live' }).click();
  await expect(page.getByTestId('day-clock')).not.toHaveText('10:00:00');
  const max = Number(await page.getByLabel('History time').getAttribute('max'));
  expect(max).toBeGreaterThan(36000000);
  expect(max).toBeLessThan(36060000);
});

test('tram and construction geometry grow on zoom instead of shrinking to a pixel cap', async ({
  page,
}) => {
  await page.goto('/');
  await page.getByRole('button', { name: '08:00 to 10:00' }).click();
  await page.getByRole('button', { name: '3D', exact: true }).click();
  await expect(page.getByTestId('map')).toHaveAttribute(
    'data-models',
    'ready',
    { timeout: 15000 },
  );
  await page.getByRole('button', { name: 'Layers', exact: true }).click();
  for (const name of ['weather', 'buildings'])
    await page.getByRole('checkbox', { name, exact: true }).uncheck();
  await page.getByRole('button', { name: 'Layers', exact: true }).click();
  async function modelAreas() {
    const png = await page.getByTestId('map').locator('canvas').screenshot();
    return page.evaluate(async (bytes) => {
      const image = await createImageBitmap(
        new Blob([new Uint8Array(bytes)], { type: 'image/png' }),
      );
      const canvas = new OffscreenCanvas(image.width, image.height);
      const ctx = canvas.getContext('2d')!;
      ctx.drawImage(image, 0, 0);
      const { data, width, height } = ctx.getImageData(
        0,
        0,
        image.width,
        image.height,
      );
      return ['tram', 'crane'].map((kind) => {
        const mask = new Uint8Array(width * height);
        for (let i = 0; i < mask.length; i++) {
          // Exclude fixed UI highlights: measure only model geometry on the map.
          if (
            i % width > width - 80 ||
            Math.floor(i / width) < 160 ||
            Math.floor(i / width) > height - 280
          )
            continue;
          const [r, g, b] = data.slice(i * 4, i * 4 + 3);
          mask[i] = Number(
            kind === 'tram'
              ? r < g * 0.65 && g > b * 1.02 && g > 60
              : r > g * 1.15 && g > b * 1.8 && g > 65,
          );
        }
        let biggest = 0;
        for (let i = 0; i < mask.length; i++) {
          if (!mask[i]) continue;
          const queue = [i];
          mask[i] = 0;
          let size = 0;
          while (queue.length) {
            const j = queue.pop()!;
            size++;
            for (const n of [
              j - width,
              j + width,
              ...(j % width ? [j - 1] : []),
              ...(j % width < width - 1 ? [j + 1] : []),
            ]) {
              if (n >= 0 && n < mask.length && mask[n]) {
                mask[n] = 0;
                queue.push(n);
              }
            }
          }
          biggest = Math.max(biggest, size);
        }
        return biggest;
      });
    }, Array.from(png));
  }
  const before = await modelAreas();
  await page.getByRole('button', { name: 'Zoom in', exact: true }).click();
  await page.waitForTimeout(500);
  const after = await modelAreas();
  for (let i = 0; i < 2; i++) {
    expect(before[i]).toBeGreaterThan(5);
    expect(after[i]).toBeGreaterThan(before[i] * 1.3);
  }
});

test('3D models reach ready while Live continuously advances and after restoring context', async ({
  page,
}) => {
  test.setTimeout(60000);
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await page.goto('/');
  await page.getByRole('button', { name: '3D', exact: true }).click();
  await expect(page.getByTestId('map')).toHaveAttribute(
    'data-models',
    'ready',
    { timeout: 15000 },
  );
  const clock = await page.getByTestId('day-clock').innerText();
  await expect(page.getByTestId('day-clock')).not.toHaveText(clock);
  await expect(
    page.getByRole('button', { name: /^Select Route .* on map$/ }),
  ).toHaveCount(0);
  const ext = await page
    .getByTestId('map')
    .locator('canvas')
    .evaluateHandle((canvas: HTMLCanvasElement) =>
      canvas.getContext('webgl2')!.getExtension('WEBGL_lose_context')!,
    );
  await ext.evaluate((e) => e.loseContext());
  await expect(
    page.getByText('Map unavailable.', { exact: false }),
  ).toBeVisible();
  await ext.evaluate((e) => e.restoreContext());
  await expect(page.getByTestId('map')).toHaveAttribute(
    'data-models',
    'ready',
    { timeout: 15000 },
  );
  await expect(
    page.getByText('Map unavailable.', { exact: false }),
  ).toHaveCount(0);
  await ext.dispose();
});

test('seeking after Live advances retains its rolling window and plays history', async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await page.goto('/');
  await expect(page.getByTestId('day-clock')).toBeVisible();
  await page.clock.install();
  await page.clock.fastForward(30 * 60_000);
  await expect(page.getByTestId('day-clock')).toHaveText(/^10:30:/);
  await page.getByLabel('History time').fill(String((10 * 60 + 20) * 60_000));
  await expect(page.getByTestId('day-clock')).toHaveText('10:20:00');
  const slider = page.getByLabel('History time');
  expect(Number(await slider.getAttribute('min'))).toBeGreaterThanOrEqual(
    8.5 * 3600000,
  );
  expect(Number(await slider.getAttribute('max'))).toBeGreaterThanOrEqual(
    10.5 * 3600000,
  );
  await page.getByRole('button', { name: 'Play demo', exact: true }).click();
  await page.clock.runFor(1000);
  await expect(page.getByTestId('day-clock')).toHaveText(/^10:20:/);
  await expect(page.getByTestId('day-clock')).not.toHaveText('10:20:00');
  await expect(page.getByRole('button', { name: 'Go live' })).not.toHaveClass(
    /at-live/,
  );
  await page.getByRole('button', { name: 'Go live' }).click();
  await page.getByRole('button', { name: '06:00 to 08:00' }).click();
  await expect(page.getByTestId('day-clock')).toHaveText('06:00:00');
  await expect(slider).toHaveAttribute('min', String(6 * 3600000));
});

test('reentering 3D resets readiness before replacing flat markers', async ({
  page,
}) => {
  await page.goto('/');
  await page.getByRole('button', { name: '3D', exact: true }).click();
  await expect(page.getByTestId('map')).toHaveAttribute(
    'data-models',
    'ready',
    { timeout: 15000 },
  );
  await page.getByRole('button', { name: '2D', exact: true }).click();
  await expect(
    page.getByRole('button', { name: /^Select Route .* on map$/ }).first(),
  ).toBeVisible();
  const changes = await page.getByTestId('map').evaluateHandle((map) => {
    const values: (string | null)[] = [];
    const observer = new MutationObserver((records) => {
      for (const record of records) values.push(record.oldValue);
    });
    observer.observe(map, {
      attributes: true,
      attributeOldValue: true,
      attributeFilter: ['data-models'],
    });
    return { values, observer };
  });
  await page.getByRole('button', { name: '3D', exact: true }).click();
  await expect(page.getByTestId('map')).toHaveAttribute(
    'data-models',
    'ready',
    { timeout: 15000 },
  );
  expect(
    await changes.evaluate(({ values, observer }) => {
      observer.disconnect();
      return values;
    }),
  ).toEqual(['hidden', 'loading']);
  await changes.dispose();
});

test('crossing the mobile breakpoint preserves the map and keeps controls outside the panel', async ({
  page,
}) => {
  await page.goto('/');
  await page.getByRole('button', { name: '08:00 to 10:00' }).click();
  const canvas = await page
    .getByTestId('map')
    .locator('canvas')
    .elementHandle();
  for (const size of [
    { width: 900, height: 1100 },
    { width: 1100, height: 900 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(size);
    await expect
      .poll(() =>
        page.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
      )
      .toBe(true);
    const zoom = page.getByRole('button', { name: 'Zoom in', exact: true });
    await expect(zoom).toBeVisible();
    await expect
      .poll(async () => {
        const a = (await zoom.boundingBox())!,
          b = (await page
            .getByRole('complementary', { name: 'Area information' })
            .boundingBox())!;
        return a.x + a.width <= b.x || a.y + a.height <= b.y;
      })
      .toBe(true);
    expect(await canvas!.evaluate((node) => node.isConnected)).toBe(true);
    await expect(page.getByTestId('day-clock')).toHaveText('08:00:00');
  }
});
