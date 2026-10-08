import { chromium, expect } from '@playwright/test';
import { fileURLToPath } from 'node:url';

const browser = await chromium.launch({
  args: ['--enable-unsafe-swiftshader'],
});
try {
  const page = await browser.newPage({
    viewport: { width: 1600, height: 1000 },
    deviceScaleFactor: 1,
    reducedMotion: 'no-preference',
  });
  await page.goto('http://127.0.0.1:5182/urban-pulse-au/?demo=health');
  await page
    .getByRole('heading', { name: 'CBD + Southbank', level: 1 })
    .waitFor();
  await page.getByRole('button', { name: '3D', exact: true }).click();
  await page.waitForFunction(
    () =>
      document
        .querySelector('[data-testid="map"]')
        ?.getAttribute('data-models') === 'ready',
  );
  await page.waitForFunction(
    () =>
      document.querySelector('[data-testid="day-clock"]')?.textContent ===
      '09:15:00',
  );
  await page.waitForFunction(
    () =>
      document
        .querySelector('[data-testid="map"]')
        ?.getAttribute('data-buildings') === 'ready',
  );
  await page.getByRole('button', { name: 'Zoom in', exact: true }).click();
  // Allow the map's camera transition and GPU frame to settle before capture.
  await page.waitForTimeout(1000);
  await page.evaluate(() => document.fonts.ready);
  await expect(
    page.getByRole('button', { name: 'Play demo', exact: true }),
  ).toBeEnabled();
  await expect(page.getByTestId('day-clock')).toHaveText('09:15:00');
  await expect(
    page.getByText('Reduced motion · use the time slider', { exact: true }),
  ).toHaveCount(0);
  await page.screenshot({
    path: fileURLToPath(
      new URL('../../../docs/images/urbanpulse-app.jpg', import.meta.url),
    ),
    type: 'jpeg',
    quality: 88,
  });
} finally {
  await browser.close();
}
