import { expect, test } from '@playwright/test';
test('demo health explains impacts, locates them and recovers without inventing a score', async ({
  page,
}) => {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.goto('./?demo=health');
  await expect(
    page.getByRole('heading', { name: 'Major disruption', exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole('group', { name: 'Choose health area' }),
  ).toContainText('Local impacts');
  await expect(page.locator('.demo-delay-affected').first()).toBeVisible();
  await expect(page.locator('.demo-delay-severe').first()).toBeVisible();
  await page.getByRole('button', { name: /Severe tram delays.*since/ }).click();
  await expect(page.getByLabel('Located demo impact')).toContainText(
    'not affected live operations',
  );
  await page.getByRole('button', { name: 'Close impact' }).click();
  await page.getByRole('button', { name: 'Recovered 09:36' }).click();
  await expect(
    page.getByRole('heading', { name: 'No known impacts', exact: true }),
  ).toBeVisible();
  await expect(page.locator('.demo-delay-severe')).toHaveCount(0);
  await expect(page.locator('.demo-delay-affected')).toHaveCount(0);
  await page.getByText('Method & area profile', { exact: true }).click();
  await expect(page.locator('.health-profile')).toContainText(
    'does not lower health',
  );
  await page.getByRole('button', { name: 'Missing data 09:50' }).click();
  await expect(
    page.getByRole('region', { name: 'CBD demo condition' }),
  ).toContainText('Data incomplete');
  await expect(page.locator('.condition-coverage')).toContainText('1/2');
  await page.getByRole('button', { name: 'Major impact 09:15' }).click();
  await expect(
    page.getByRole('heading', { name: 'Major disruption', exact: true }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});
test('street-name toggle and 2D/3D delay overlays work on the static site', async ({
  page,
}) => {
  await page.goto('./?demo=health');
  await expect(
    page.locator('.sample-map-label').filter({ hasText: 'Collins Street' }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Layers', exact: true }).click();
  await page.getByRole('checkbox', { name: 'Main street names' }).uncheck();
  await expect(
    page.locator('.sample-map-label').filter({ hasText: 'Collins Street' }),
  ).toBeHidden();
  await page.getByRole('checkbox', { name: 'Main street names' }).check();
  await page.getByRole('button', { name: 'Layers', exact: true }).click();
  await expect(
    page.locator('.sample-project.construction img').first(),
  ).toHaveAttribute('src', /construction-/);
  await expect(
    page.locator('.sample-project.planned img').first(),
  ).toHaveAttribute('src', /development-plan-/);
  await page.locator('.demo-delay-severe').first().click();
  await expect(page.locator('.tram-delay-detail')).toContainText(
    'Severe tram delays',
  );
  await page.getByRole('button', { name: '3D', exact: true }).click();
  await expect(page.getByTestId('map')).toHaveAttribute(
    'data-models',
    'ready',
    { timeout: 20000 },
  );
  await expect(page.locator('.demo-delay-severe')).toHaveCount(0);
  await expect(
    page.getByText('Severe demo delay', { exact: true }),
  ).toBeVisible();
  await page.screenshot({ path: 'test-results/health-3d.png' });
  await page.getByRole('button', { name: '2D', exact: true }).click();
  await expect(page.locator('.demo-delay-severe').first()).toBeVisible();
  await expect(
    page.locator('.sample-map-label').filter({ hasText: 'Collins Street' }),
  ).toBeVisible();
  await page.screenshot({ path: 'test-results/health-2d.png' });
});
