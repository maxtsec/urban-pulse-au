import { expect, test } from '@playwright/test';
import type { Page } from '@playwright/test';
import { chooseScenario, moment } from './helpers';

async function setup(page: Page) {
  const start = new Date('2026-01-01T00:00:00Z');
  await page.clock.install({ time: start });
  await page.goto('/tests/scenario.html?scenario=journey');
  await expect(page.getByTestId('clock')).toHaveText('11:00:00');
  // Freeze elapsed time: CI/browser work must not consume the debounce window.
  await page.clock.pauseAt(new Date(start.getTime() + 60_000));
  const requests: string[] = [];
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (url.pathname.endsWith('/au-vic-melbourne-clue-southbank'))
      requests.push(
        `${url.searchParams.get('scenario')}:${url.searchParams.get('seconds')}`,
      );
  });
  return requests;
}

async function expectSnapshot(page: Page, time: string) {
  // Network responses arrive on real time; flush their queued query notifications
  // without allowing wall-clock delays to advance playback or debounce timers.
  await expect
    .poll(async () => {
      await page.clock.runFor(1);
      return page.getByTestId('clock').textContent();
    })
    .toBe(time);
}

test('rapid scrubbing previews each choice but requests only the settled final time', async ({
  page,
}) => {
  const requests = await setup(page);
  const slider = page.getByLabel('Scenario time', { exact: true });
  for (const seconds of ['30', '90', '180', '300', '120']) {
    await slider.fill(seconds);
    await expect(slider).toHaveValue(seconds);
    await page.clock.runFor(40);
  }
  expect(requests).toEqual([]);
  await expect(page.getByTestId('clock')).toHaveText('11:00:00');
  await page.clock.runFor(250);
  await expectSnapshot(page, '11:02:00');
  expect(requests).toEqual(['journey:120']);
});

test('reset and direct moments cancel a pending scrub', async ({ page }) => {
  const requests = await setup(page);
  const slider = page.getByLabel('Scenario time', { exact: true });
  await slider.fill('180');
  await page.getByRole('button', { name: 'Reset', exact: true }).click();
  await page.clock.runFor(300);
  await expect(slider).toHaveValue('0');
  expect(requests).toEqual([]);
  await slider.fill('180');
  await moment(page, '30s · Position update').click();
  await expectSnapshot(page, '11:00:30');
  await page.clock.runFor(300);
  expect(requests).toEqual(['journey:30']);
});

test('scenario navigation cancels the old pending scrub', async ({ page }) => {
  const requests = await setup(page);
  await page.getByLabel('Scenario time', { exact: true }).fill('180');
  await chooseScenario(page, 'City overview');
  await page.clock.runFor(300);
  await expect.poll(() => requests.length).toBe(1);
  expect(requests).toEqual(['city:0']);
  await expect(page.getByLabel('Scenario time', { exact: true })).toHaveValue(
    '0',
  );
});

test('Play commits the selected time and keeps the normal playback interval', async ({
  page,
}) => {
  const requests = await setup(page);
  await page.getByLabel('Scenario time', { exact: true }).fill('120');
  await page
    .getByRole('button', { name: 'Play scenario', exact: true })
    .click();
  await expectSnapshot(page, '11:02:00');
  await page.clock.runFor(300);
  expect(requests).toEqual(['journey:120']);
  await page.clock.runFor(2000);
  await expectSnapshot(page, '11:02:15');
  expect(requests).toEqual(['journey:120', 'journey:135']);
});
