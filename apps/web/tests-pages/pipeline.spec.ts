import { expect, test } from '@playwright/test';

test('mock trends compare areas and keep partial and missing intervals explicit', async ({
  page,
}) => {
  const api: string[] = [];
  page.on('request', (request) => {
    if (new URL(request.url()).pathname.startsWith('/api/'))
      api.push(request.url());
  });
  await page.goto('./?demo=health');
  const clock = await page.getByTestId('day-clock').textContent();
  await page.getByRole('button', { name: /Data & pipeline/ }).click();
  const dialog = page.getByRole('dialog', {
    name: 'From observations to insight',
  });
  await expect(dialog).toContainText('MOCK · NOT CONNECTED');
  await expect(dialog).toContainText('7 Oct 2026 · 08:00–10:00');
  await expect(page.getByTestId('mock-vehicles')).toHaveText('49');
  await page
    .getByRole('group', { name: 'Choose metric area' })
    .getByRole('button', { name: 'Southbank' })
    .click();
  await expect(page.getByTestId('mock-vehicles')).toHaveText('25');
  await page.getByRole('button', { name: /^08:45 to 09:00:/ }).click();
  await expect(page.getByTestId('mock-captures')).toHaveText('10/15');
  await expect(dialog.locator('.pipeline-reading')).toContainText(
    'Compare this interval with care',
  );
  await page.getByRole('button', { name: /^09:00 to 09:15:/ }).click();
  await expect(page.getByTestId('mock-vehicles')).toHaveText('N/A');
  await expect(page.getByTestId('mock-freshness')).toHaveText('N/A');
  await expect(page.getByTestId('mock-captures')).toHaveText('0/15');
  await expect(dialog).toContainText('missing data, not an empty city');
  await page.getByRole('button', { name: /^09:15 to 09:30:/ }).click();
  await expect(page.getByTestId('mock-vehicles')).toHaveText('23');
  await expect(page.getByTestId('mock-freshness')).toHaveText('104 s');
  await page.screenshot({ path: 'test-results/pipeline-trends.png' });
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
  await expect(
    page.getByRole('button', { name: /Data & pipeline/ }),
  ).toBeFocused();
  await expect(page.getByTestId('day-clock')).toHaveText(clock!);
  expect(api).toEqual([]);
});

test('engineering examples are illustrative, keyboard navigable and usable on a phone', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('./?demo=health');
  await page.getByRole('button', { name: /Data & pipeline/ }).click();
  const dialog = page.getByRole('dialog', {
    name: 'From observations to insight',
  });
  await page.getByRole('tab', { name: 'Trend preview' }).focus();
  await page.keyboard.press('ArrowRight');
  await expect(page.getByRole('tab', { name: 'How it works' })).toBeFocused();
  await expect(dialog).toContainText('ILLUSTRATIVE · NOT A TEST RUN');
  await expect(dialog).toContainText('120 rows · 0 extra rows');
  await page
    .getByRole('button', { name: 'Recover an upload', exact: true })
    .click();
  await expect(dialog).toContainText('One object · confirmation recorded');
  await page
    .getByRole('button', { name: 'Keep a collection gap', exact: true })
    .click();
  await expect(dialog).toContainText('Vehicle count N/A · gap retained');
  await expect(
    dialog.getByRole('link', { name: /Worker recovery evidence/ }),
  ).toHaveAttribute('href', /\/docs\/evidence\/event-01-worker-recovery.md$/);
  expect(await dialog.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(
    true,
  );
  await page.getByRole('tab', { name: 'Trend preview' }).click();
  expect(await dialog.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(
    true,
  );
  await page.screenshot({ path: 'test-results/pipeline-phone.png' });
  await page.getByRole('button', { name: 'Close data and pipeline' }).click();
  await expect(dialog).toHaveCount(0);
});
