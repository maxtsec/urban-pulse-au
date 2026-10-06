import { expect, test } from '@playwright/test';
import type { Page } from '@playwright/test';
import { chooseScenario, moment } from './helpers';

async function setup(page: Page) {
  await page.goto('/?scenario=journey');
  await expect(page.getByTestId('clock')).toHaveText('11:00:00');
  await page.clock.install();
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
  await expect(page.getByTestId('clock')).toHaveText('11:02:00');
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
  await expect(page.getByTestId('clock')).toHaveText('11:00:30');
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
  await expect(page.getByTestId('clock')).toHaveText('11:02:00');
  await page.clock.runFor(300);
  expect(requests).toEqual(['journey:120']);
  await page.clock.runFor(1700);
  await expect(page.getByTestId('clock')).toHaveText('11:02:15');
  expect(requests).toEqual(['journey:120', 'journey:135']);
});
