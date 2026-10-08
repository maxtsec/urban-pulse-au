import { expect, test } from '@playwright/test';
test('day overview jumps to a short tram incident and retains live gating', async ({
  page,
}) => {
  await page.goto('./?demo=health');
  await page.getByRole('button', { name: 'Day overview' }).click();
  const dialog = page.getByRole('dialog', { name: 'Day overview' });
  await expect(dialog).toBeVisible();
  await expect(
    dialog.getByRole('group', { name: 'CBD trams timeline' }),
  ).toBeVisible();
  await expect(
    dialog.getByRole('group', { name: 'Southbank trams timeline' }),
  ).toBeVisible();
  await expect(dialog).toContainText('work schedule');
  await expect(
    dialog.getByRole('button', { name: /Weather:.*11:00/ }),
  ).toHaveCount(0);
  await dialog
    .getByRole('button', { name: /Southbank trams: Severe delay/ })
    .click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByTestId('day-clock')).toHaveText('09:10:00');
  await expect(
    page.getByRole('region', { name: 'Southbank demo condition' }),
  ).toContainText('Major disruption');
  await page.getByRole('button', { name: 'Day overview' }).click();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog', { name: 'Day overview' })).toHaveCount(
    0,
  );
  await expect(
    page.getByRole('button', { name: 'Day overview' }),
  ).toBeFocused();
});
test('weather and development rows navigate to the corresponding panel on mobile', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('./');
  await page.getByRole('button', { name: 'Day overview' }).click();
  await page.getByRole('button', { name: /Weather: rainy/ }).click();
  await expect(page.getByTestId('day-clock')).toHaveText('09:00:00');
  await expect(
    page.getByRole('tab', { name: 'Weather', exact: true }),
  ).toHaveAttribute('aria-selected', 'true');
  await page.getByRole('button', { name: 'Day overview' }).click();
  await page
    .getByRole('button', { name: /Development:.*construction-status/ })
    .click();
  await expect(
    page.getByRole('tab', { name: 'Works', exact: true }),
  ).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByRole('tabpanel')).toContainText(
    'not actual worksite location',
  );
});
