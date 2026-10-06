import { expect, test } from '@playwright/test';
import type { Page } from '@playwright/test';
import { moment } from './helpers';

// The shared config reduces motion; these cases exercise the animated path.
test.use({ reducedMotion: 'no-preference' });

const TRAM = '[aria-label="Select Tram 01 on map"]';

type Point = { x: number; y: number };
const distance = (a: Point, b: Point) => Math.hypot(a.x - b.x, a.y - b.y);

async function tramPosition(page: Page): Promise<Point> {
  const box = (await page.locator(TRAM).boundingBox())!;
  return { x: box.x, y: box.y };
}

/** Observed positions at 0s and 30s, reached by direct seeks (no glide). */
async function observedPositions(page: Page) {
  await page.goto('/?scenario=journey');
  await expect(page.locator(TRAM)).toBeVisible();
  const start = await tramPosition(page);
  await moment(page, '30s · Position update').click();
  await expect(page.getByTestId('clock')).toHaveText('11:00:30');
  const next = await tramPosition(page);
  await page.getByRole('button', { name: 'Reset', exact: true }).click();
  await expect(page.getByTestId('clock')).toHaveText('11:00:00');
  await expect.poll(() => tramPosition(page)).toEqual(start);
  expect(distance(start, next)).toBeGreaterThan(10);
  return { start, next };
}

test('playback glides a tram between observations and advances progress continuously', async ({
  page,
}) => {
  const { start, next } = await observedPositions(page);
  const samples = await page.evaluate(async (selector) => {
    const tram = document.querySelector(selector)!;
    const fill = document.querySelector('[data-testid="playback-progress"]')!;
    const clock = document.querySelector('[data-testid="clock"]')!;
    document
      .querySelector<HTMLButtonElement>('[aria-label="Play scenario"]')!
      .click();
    const rows = [];
    const began = performance.now();
    while (performance.now() - began < 8000) {
      await new Promise(requestAnimationFrame);
      const box = tram.getBoundingClientRect();
      rows.push({
        t: performance.now() - began,
        x: box.x,
        y: box.y,
        clock: clock.textContent,
        progress: fill.getBoundingClientRect().width,
      });
    }
    document.querySelector<HTMLButtonElement>('[aria-label="Pause"]')?.click();
    return rows;
  }, TRAM);

  // The clock only shows snapshot times, never an interpolated time.
  for (const row of samples) expect(row.clock).toMatch(/^11:00:(00|15|30|45)$/);

  // Progress moves within a step instead of jumping at its end.
  const firstStep = samples.filter(
    (row) => row.clock === '11:00:00' && row.t > 200 && row.t < 1800,
  );
  expect(firstStep.at(-1)!.progress - firstStep[0].progress).toBeGreaterThan(5);

  // After the 30s observation arrives, the tram passes through intermediate points and settles on it.
  const arrival = samples.findIndex((row) => row.clock === '11:00:30');
  expect(arrival).toBeGreaterThan(0);
  const afterArrival = samples.slice(arrival);
  expect(afterArrival.at(-1)!.t - samples[arrival].t).toBeGreaterThan(1600);
  expect(
    afterArrival.some(
      (row) => distance(row, start) > 2 && distance(row, next) > 2,
    ),
  ).toBe(true);
  for (let i = 1; i < afterArrival.length; i++)
    expect(distance(afterArrival[i], next)).toBeLessThanOrEqual(
      distance(afterArrival[i - 1], next) + 0.5,
    );
  const settled = samples.find(
    (row) => row.t > samples[arrival].t + 1600 && row.clock === '11:00:30',
  );
  if (settled) expect(distance(settled, next)).toBeLessThan(1);
  // Before the observation arrives the tram stays on its earlier observation.
  for (const row of samples.slice(0, arrival))
    expect(distance(row, start)).toBeLessThan(1);
});

test('seeking places trams at their observation without gliding', async ({
  page,
}) => {
  const { next } = await observedPositions(page);
  await moment(page, '30s · Position update').click();
  await expect(page.getByTestId('clock')).toHaveText('11:00:30');
  const samples = await page.evaluate(async (selector) => {
    const rows = [];
    for (let i = 0; i < 10; i++) {
      await new Promise(requestAnimationFrame);
      const box = document.querySelector(selector)!.getBoundingClientRect();
      rows.push({ x: box.x, y: box.y });
    }
    return rows;
  }, TRAM);
  for (const row of samples) expect(distance(row, next)).toBeLessThan(1);
});

test('pausing during a glide places the tram at its observation', async ({
  page,
}) => {
  const { next } = await observedPositions(page);
  // Pause in the same frame the 30s observation appears, mid-glide.
  await page.evaluate(
    () =>
      new Promise<void>((resolve) => {
        const clock = document.querySelector('[data-testid="clock"]')!;
        new MutationObserver((_, observer) => {
          if (clock.textContent !== '11:00:30') return;
          observer.disconnect();
          requestAnimationFrame(() => {
            document
              .querySelector<HTMLButtonElement>('[aria-label="Pause"]')!
              .click();
            resolve();
          });
        }).observe(clock, {
          childList: true,
          characterData: true,
          subtree: true,
        });
        document
          .querySelector<HTMLButtonElement>('[aria-label="Play scenario"]')!
          .click();
      }),
  );
  await expect(
    page.getByRole('button', { name: 'Play scenario', exact: true }),
  ).toBeVisible();
  await expect.poll(() => tramPosition(page)).toEqual(next);
  const later = await tramPosition(page);
  await page.waitForTimeout(400);
  expect(await tramPosition(page)).toEqual(later);
});

test('enabling reduced motion during a glide immediately shows the observation', async ({
  page,
}) => {
  const { next } = await observedPositions(page);
  await page
    .getByRole('button', { name: 'Play scenario', exact: true })
    .click();
  await expect(page.getByTestId('clock')).toHaveText('11:00:30', {
    timeout: 10000,
  });
  expect(distance(await tramPosition(page), next)).toBeGreaterThan(1);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.evaluate(
    () =>
      new Promise((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(resolve)),
      ),
  );
  expect(distance(await tramPosition(page), next)).toBeLessThan(1);
});

test('moving labels remain separate from other map markers', async ({
  page,
}) => {
  await observedPositions(page);
  await page
    .getByRole('button', { name: 'Play scenario', exact: true })
    .click();
  await expect(page.getByTestId('clock')).toHaveText('11:00:30', {
    timeout: 10000,
  });
  const collisions = await page.evaluate(async () => {
    let collisions = 0;
    const start = performance.now();
    while (performance.now() - start < 1200) {
      await new Promise(requestAnimationFrame);
      const icons = [
        ...document.querySelectorAll('.tram-marker img, .development-marker'),
      ].map((node) => node.getBoundingClientRect());
      const labels = [
        ...document.querySelectorAll(
          '.tram-marker:not(.label-collapsed) .marker-label',
        ),
      ].map((node) => node.getBoundingClientRect());
      for (let i = 0; i < labels.length; i++) {
        const a = labels[i];
        for (const b of [...icons, ...labels.slice(i + 1)]) {
          if (
            a.left < b.right &&
            a.right > b.left &&
            a.top < b.bottom &&
            a.bottom > b.top
          )
            collisions++;
        }
      }
    }
    return collisions;
  });
  expect(collisions).toBe(0);
});

test('reduced motion progress stays on the displayed snapshot', async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/?scenario=journey');
  await expect(page.getByTestId('clock')).toHaveText('11:00:00');
  const fill = page.getByTestId('playback-progress');
  const initial = (await fill.boundingBox())!.width;
  await page
    .getByRole('button', { name: 'Play scenario', exact: true })
    .click();
  await page.waitForTimeout(250);
  await expect(page.getByTestId('clock')).toHaveText('11:00:00');
  expect((await fill.boundingBox())!.width).toBe(initial);
  await expect(page.getByTestId('clock')).toHaveText('11:00:15');
  const width = (await page.locator('.slider-rail').boundingBox())!.width;
  expect((await fill.boundingBox())!.width).toBeCloseTo((width * 15) / 360, 1);
});

test('3D keeps tram markers at observations instead of using the temporary 2D glide', async ({
  page,
}) => {
  await page.goto('/?scenario=journey');
  await expect(page.locator(TRAM)).toBeVisible();
  await page.getByRole('button', { name: '3D view', exact: true }).click();
  await expect(page.getByTestId('map')).toHaveAttribute(
    'data-buildings',
    'ready',
  );
  await page
    .getByRole('button', { name: 'Play scenario', exact: true })
    .click();
  await expect(page.getByTestId('clock')).toHaveText('11:00:30', {
    timeout: 8000,
  });
  const samples = await page.evaluate(async (selector) => {
    const rows = [];
    const started = performance.now();
    while (performance.now() - started < 400) {
      await new Promise(requestAnimationFrame);
      const box = document.querySelector(selector)!.getBoundingClientRect();
      rows.push({ x: box.x, y: box.y });
    }
    return rows;
  }, TRAM);
  await page.getByRole('button', { name: 'Pause', exact: true }).click();
  const observed = await tramPosition(page);
  for (const sample of samples)
    expect(distance(sample, observed)).toBeLessThan(1);
});
