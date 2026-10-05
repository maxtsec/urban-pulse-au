import { expect, test } from '@playwright/test';
import { mkdir } from 'node:fs/promises';

test('weather lifecycle changes the area view and map with independent coverage', async ({
  page,
}) => {
  const external: string[] = [];
  const errors: string[] = [];
  page.on('request', (request) => {
    if (
      /^https?:/.test(request.url()) &&
      new URL(request.url()).hostname !== '127.0.0.1'
    )
      external.push(request.url());
  });
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/');
  await page
    .getByRole('combobox', { name: 'Scenario', exact: true })
    .selectOption('weather');
  const details = page.getByRole('region', { name: 'Weather details' });
  await expect(details.getByText('Modelled weather information')).toBeVisible();
  await expect(page.locator('.condition-box strong')).toHaveText('Unknown');
  await page.getByRole('button', { name: '30s · Advice', exact: true }).click();
  await expect(page.locator('.condition-box strong')).toHaveText('Normal');
  await expect(
    details.getByText('Informational warning; not a degradation reason.'),
  ).toBeVisible();
  await expect(page.getByTestId('warning-map-count')).toHaveText(
    '1 active warning areas',
  );
  await page
    .getByRole('checkbox', { name: 'Warning areas', exact: true })
    .uncheck();
  await expect(page.getByTestId('warning-map-count')).toHaveCount(0);
  await expect(details.getByRole('article')).toHaveCount(1);
  await page
    .getByRole('checkbox', { name: 'Warning areas', exact: true })
    .check();
  await page
    .getByRole('button', { name: '60s · Watch and Act', exact: true })
    .click();
  await expect(page.locator('.condition-box strong')).toHaveText('Degraded');
  await expect(page.locator('.reason')).toHaveCount(2);
  await page
    .getByRole('button', { name: '150s · Cancelled', exact: true })
    .click();
  await expect(details.getByText('cancelled', { exact: true })).toBeVisible();
  await expect(page.locator('.reason')).toHaveCount(1);
  await expect(page.getByTestId('warning-map-count')).toHaveText(
    '0 active warning areas',
  );
  await page
    .getByRole('button', { name: '180s · Emergency Warning', exact: true })
    .click();
  await expect(page.locator('.reason')).toHaveCount(1);
  await expect(page.locator('.reason')).toContainText('Emergency Warning');
  await expect(page.getByTestId('warning-map-count')).toHaveText(
    '1 active warning areas',
  );
  await mkdir('../../.local/city02', { recursive: true });
  await page.screenshot({
    path: '../../.local/city02/weather-desktop.png',
    fullPage: true,
  });
  await page
    .getByRole('button', {
      name: '240s · Expired, coverage stale',
      exact: true,
    })
    .click();
  await expect(page.locator('.condition-box strong')).toHaveText('Unknown');
  await expect(details.locator('.warning-heading').first()).toContainText(
    'stale',
  );
  await expect(details.getByText('expired', { exact: true })).toBeVisible();
  await page
    .getByRole('button', { name: '270s · Coverage restored', exact: true })
    .click();
  await expect(page.locator('.condition-box strong')).toHaveText('Normal');
  await page
    .getByRole('button', { name: '330s · Incomplete coverage', exact: true })
    .click();
  await expect(page.locator('.condition-box strong')).toHaveText('Unknown');
  await expect(details.getByText(/Area applicability unknown/)).toBeVisible();
  expect(errors).toEqual([]);
  expect(external).toEqual([]);
});

test('outage keeps received warning and attribution without leaking cancellation', async ({
  page,
}) => {
  await page.goto('/');
  await page
    .getByRole('combobox', { name: 'Scenario', exact: true })
    .selectOption('weather-outage');
  await page
    .getByRole('button', { name: '180s · Emergency Warning', exact: true })
    .click();
  const details = page.getByRole('region', { name: 'Weather details' });
  await expect(page.locator('.condition-box strong')).toHaveText('Degraded');
  await expect(
    details.getByText('Watch and Act', { exact: true }),
  ).toBeVisible();
  await expect(details).not.toContainText('cancelled');
  await expect(details.locator('.weather-credit')).toContainText(
    'State of Victoria',
  );
  await expect(
    details.getByRole('link', { name: 'EMV emergency-data notice' }),
  ).toHaveAttribute(
    'href',
    'https://www.emv.vic.gov.au/responsibilities/victorias-warning-system/emergency-data',
  );
  await expect(details.locator('.weather-receipt')).toContainText('11:01:00');
  await expect(details.locator('.weather-receipt')).toContainText('2026');
  await expect(details.locator('.weather-receipt')).toContainText(
    /AEDT|GMT\+11/,
  );
  await page
    .getByRole('button', {
      name: '240s · Expired, coverage stale',
      exact: true,
    })
    .click();
  await expect(page.locator('.condition-box strong')).toHaveText('Unknown');
  await expect(details.locator('.weather-receipt')).toContainText('11:01:00');
  await expect(details.locator('.warning-heading').first()).toContainText(
    'error',
  );
});

test('weather details are usable on a small screen and replay keeps original receipt date', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await page
    .getByRole('combobox', { name: 'Scenario', exact: true })
    .selectOption('weather');
  await page
    .getByRole('button', { name: '270s · Coverage restored', exact: true })
    .click();
  await expect(page.locator('.condition-box strong')).toHaveText('Normal');
  await page.getByRole('button', { name: '30s · Advice', exact: true }).click();
  await expect(page.locator('.weather-receipt')).toContainText('11:00:30');
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await mkdir('../../.local/city02', { recursive: true });
  await page.screenshot({
    path: '../../.local/city02/weather-mobile.png',
    fullPage: true,
  });
});
