import { expect, test } from '@playwright/test';
import { writeFile } from 'node:fs/promises';

test.setTimeout(90_000);
test.skip(
  process.env.URBANPULSE_MEASURE_BUILDINGS !== '1',
  'Opt-in rendering diagnostics; not a performance acceptance gate',
);

for (const profile of ['desktop', 'mobile'] as const) {
  test(`measure building rendering on ${profile}`, async ({
    browser,
  }, info) => {
    const context = await browser.newContext({
      baseURL: info.project.use.baseURL,
      viewport:
        profile === 'desktop'
          ? { width: 1440, height: 1100 }
          : { width: 390, height: 844 },
      deviceScaleFactor: profile === 'desktop' ? 1 : 2,
      isMobile: profile === 'mobile',
      hasTouch: profile === 'mobile',
      reducedMotion: 'reduce',
    });
    const page = await context.newPage();
    const session = await context.newCDPSession(page);
    await session.send('Performance.enable');
    const memory = async () => {
      const { metrics } = await session.send('Performance.getMetrics');
      return metrics.find(
        (metric: { name: string }) => metric.name === 'JSHeapUsedSize',
      )!.value;
    };
    try {
      await page.goto('/tests/scenario.html?scenario=city');
      await expect(
        page.getByRole('button', {
          name: 'Select Tram 01 on map',
          exact: true,
        }),
      ).toBeVisible();
      const before = await memory();
      const start = Date.now();
      await page.getByRole('button', { name: '3D view', exact: true }).click();
      await expect(page.getByTestId('map')).toHaveAttribute(
        'data-buildings',
        'ready',
      );
      const readyMs = Date.now() - start;
      const after = await memory();
      const sampling = page.evaluate(
        () =>
          new Promise<number[]>((resolve) => {
            const gaps: number[] = [];
            const started = performance.now();
            let previous = started;
            function frame(now: number) {
              gaps.push(now - previous);
              previous = now;
              if (now - started < 2000) requestAnimationFrame(frame);
              else resolve(gaps);
            }
            requestAnimationFrame(frame);
          }),
      );
      const box = (await page.getByTestId('map').boundingBox())!;
      const x = box.x + box.width * 0.4;
      const y = box.y + box.height * 0.5;
      await page.mouse.move(x, y);
      await page.mouse.down({ button: 'right' });
      for (let i = 1; i <= 20; i++) {
        await page.mouse.move(x + i * 2, y + Math.sin(i / 3) * 8);
        await page.waitForTimeout(75); // Fixed measurement interval, not a readiness assertion.
      }
      await page.mouse.up({ button: 'right' });
      const gaps = await sampling;
      const sorted = [...gaps].sort((a, b) => a - b);
      const result = {
        profile,
        browser: browser.version(),
        renderer: await page.evaluate(() => {
          const gl = document.querySelector('canvas')!.getContext('webgl2')!;
          const extension = gl.getExtension('WEBGL_debug_renderer_info');
          return extension
            ? gl.getParameter(extension.UNMASKED_RENDERER_WEBGL)
            : 'unavailable';
        }),
        ready_ms: readyMs,
        js_heap_before_bytes: before,
        js_heap_after_bytes: after,
        raf_samples: gaps.length,
        raf_hz: (1000 * gaps.length) / gaps.reduce((sum, n) => sum + n, 0),
        raf_gap_p95_ms: sorted[Math.floor(sorted.length * 0.95)],
        limitation:
          'Browser RAF cadence during camera input, not GPU frame completion; JS heap excludes GPU/process memory. Mobile is emulated, not device hardware.',
      };
      const file = info.outputPath('measurement.json');
      await writeFile(file, JSON.stringify(result, null, 2));
      await info.attach('building-rendering-measurement', {
        path: file,
        contentType: 'application/json',
      });
      await page.screenshot({
        path: info.outputPath(`buildings-${profile}.png`),
        fullPage: true,
      });
      expect(result.raf_samples).toBeGreaterThan(0);
    } finally {
      await context.close();
    }
  });
}
