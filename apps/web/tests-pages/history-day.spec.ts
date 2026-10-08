import { test, expect } from '@playwright/test';
test('previous day unlocks 24 hours, has distinct conditions and returns to bounded today', async ({
  page,
}) => {
  await page.goto('./');
  const map = page.getByTestId('map');
  await expect(map).toBeVisible();
  await page.evaluate(() => {
    (window as unknown as { originalMap: Element | null }).originalMap =
      document.querySelector('[data-testid="map"]');
  });
  await page
    .getByRole('combobox', { name: 'Sample date' })
    .selectOption('previous');
  await expect(
    page.getByRole('button', { name: '22:00 to 24:00' }),
  ).toBeEnabled();
  await page.getByRole('button', { name: '22:00 to 24:00' }).click();
  await page.getByRole('slider', { name: 'History time' }).fill('81000000');
  await page.getByRole('button', { name: /CBD Local impacts/ }).click();
  await expect(
    page.getByRole('region', { name: 'CBD demo condition' }),
  ).toContainText('Local impacts');
  await expect(
    page.getByRole('region', { name: 'Demo affected-trip share' }),
  ).not.toContainText('N/A');
  expect(
    await page.evaluate(
      () =>
        document.querySelector('[data-testid="map"]') ===
        (window as unknown as { originalMap: Element | null }).originalMap,
    ),
  ).toBe(true);
  await page.getByRole('button', { name: 'Day overview' }).click();
  const dialog = page.getByRole('dialog', { name: 'Day overview' });
  await expect(dialog).toContainText('7 October 2026');
  await expect(dialog.getByLabel('Future times unavailable')).toHaveCount(0);
  await expect(
    dialog.getByRole('region', { name: 'Timetable details' }),
  ).toContainText('22:15–23:00');
  await dialog.evaluate((el) => {
    el.scrollTop = el.scrollHeight;
  });
  const close = dialog.getByRole('button', { name: 'Close day overview' });
  await expect(close).toBeInViewport();
  await close.click();
  await page.getByRole('button', { name: 'Missing data 20:15' }).click();
  await expect(
    page.getByRole('region', { name: 'Demo affected-trip share' }),
  ).toContainText('N/A');
  await page.getByRole('button', { name: 'Go live' }).click();
  await expect(page.getByRole('combobox', { name: 'Sample date' })).toHaveValue(
    'today',
  );
  await expect(
    page.getByRole('button', { name: '22:00 to 24:00' }),
  ).toBeDisabled();
});
test('previous day ends in history instead of silently changing to Live', async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await page.goto('./');
  await page
    .getByRole('combobox', { name: 'Sample date' })
    .selectOption('previous');
  await page.getByRole('button', { name: '22:00 to 24:00' }).click();
  await page.getByRole('slider', { name: 'History time' }).fill('86399000');
  await page
    .getByRole('combobox', { name: 'Playback speed' })
    .selectOption('300');
  await page.getByRole('button', { name: 'Play demo' }).click();
  await expect(page.getByTestId('day-clock')).toHaveText('24:00:00');
  await expect(page.getByRole('button', { name: 'Go live' })).toHaveAttribute(
    'aria-pressed',
    'false',
  );
  await expect(page.getByRole('combobox', { name: 'Sample date' })).toHaveValue(
    'previous',
  );
});

test('previous-day schedule loads only on selection, caches success and cannot override Go live', async ({
  page,
}) => {
  let downloads = 0;
  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route('**/previous-schedule-*.json', async (route) => {
    downloads += 1;
    await gate;
    await route.continue();
  });
  await page.goto('./');
  await expect(page.getByTestId('map')).toBeVisible();
  expect(downloads).toBe(0);
  await page
    .getByRole('combobox', { name: 'Sample date' })
    .selectOption('previous');
  await expect(
    page.locator('.sample-load-notice[role="status"]'),
  ).toContainText('Loading and verifying 7 October');
  await expect.poll(() => downloads).toBe(1);
  await page.getByRole('button', { name: 'Go live' }).click();
  const response = page.waitForResponse(/previous-schedule-.*json/);
  release();
  await response;
  await expect(page.getByRole('combobox', { name: 'Sample date' })).toHaveValue(
    'today',
  );
  await expect(
    page.getByRole('button', { name: '22:00 to 24:00' }),
  ).toBeDisabled();
  await page
    .getByRole('combobox', { name: 'Sample date' })
    .selectOption('previous');
  await expect(
    page.getByRole('button', { name: '22:00 to 24:00' }),
  ).toBeEnabled();
  await page.getByRole('button', { name: 'Go live' }).click();
  await page
    .getByRole('combobox', { name: 'Sample date' })
    .selectOption('previous');
  await expect(
    page.getByRole('button', { name: '22:00 to 24:00' }),
  ).toBeEnabled();
  expect(downloads).toBe(1);
});

test('a corrupt previous-day schedule preserves the current map and can be retried', async ({
  page,
}) => {
  let attempts = 0;
  await page.route('**/previous-schedule-*.json', async (route) => {
    attempts += 1;
    if (attempts === 1) await route.fulfill({ status: 200, body: '{}' });
    else await route.continue();
  });
  await page.goto('./?demo=health');
  await expect(page.getByTestId('day-clock')).toHaveText('09:15:00');
  await page
    .getByRole('combobox', { name: 'Sample date' })
    .selectOption('previous');
  await expect(page.getByRole('alert')).toContainText(
    '7 October could not be verified',
  );
  await expect(page.getByTestId('day-clock')).toHaveText('09:15:00');
  await expect(page.getByRole('combobox', { name: 'Sample date' })).toHaveValue(
    'today',
  );
  await expect(page.getByTestId('map')).toBeVisible();
  await page.getByRole('button', { name: 'Retry previous day' }).click();
  await expect(
    page.getByRole('button', { name: '22:00 to 24:00' }),
  ).toBeEnabled();
  await expect(page.getByRole('alert')).toHaveCount(0);
  expect(attempts).toBe(2);
});
