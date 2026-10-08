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
