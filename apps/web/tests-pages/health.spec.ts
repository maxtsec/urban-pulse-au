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
    page.locator('.sample-street-label').filter({ visible: true }).first(),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Layers', exact: true }).click();
  await page.getByRole('checkbox', { name: 'Main street names' }).uncheck();
  await expect(
    page.locator('.sample-street-label').filter({ visible: true }),
  ).toHaveCount(0);
  await page.getByRole('checkbox', { name: 'Main street names' }).check();
  await page.getByRole('button', { name: 'Layers', exact: true }).click();
  await expect(
    page.locator('.sample-project.construction img').first(),
  ).toHaveAttribute('src', /construction-/);
  await expect(page.locator('.sample-project.planned')).toHaveCount(0);
  await page.getByRole('button', { name: 'Layers', exact: true }).click();
  await page
    .getByRole('checkbox', { name: 'Other development projects' })
    .check();
  await expect(
    page.locator('.sample-project.planned img').first(),
  ).toHaveAttribute('src', /development-plan-/);
  await page
    .getByRole('checkbox', { name: 'Other development projects' })
    .uncheck();
  await expect(page.locator('.sample-project.planned')).toHaveCount(0);
  await page.getByRole('button', { name: 'Layers', exact: true }).click();
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
    page.locator('.sample-street-label').filter({ visible: true }).first(),
  ).toBeVisible();
  await page.screenshot({ path: 'test-results/health-2d.png' });
});

test('ordinary tram labels stay quiet until focus, selection or close zoom', async ({
  page,
}) => {
  await page.goto('./?demo=health');
  const quiet = page.locator('.tram-marker.label-quiet').first();
  await expect(quiet).toBeVisible();
  await expect(quiet.locator('.marker-label')).toHaveCSS('opacity', '0');
  await quiet.focus();
  await expect(quiet.locator('.marker-label')).toHaveCSS('opacity', '1');
  await quiet.press('Enter');
  await expect(page.locator('.tram-marker.selected .marker-label')).toHaveCSS(
    'opacity',
    '1',
  );
  await expect(page.locator('.demo-delay-severe.label-quiet')).toHaveCount(0);
  await page.getByRole('button', { name: 'Zoom in', exact: true }).click();
  await page.getByRole('button', { name: 'Zoom in', exact: true }).click();
  await page.getByRole('button', { name: 'Zoom in', exact: true }).click();
  await page.getByRole('button', { name: 'Zoom in', exact: true }).click();
  await expect(page.locator('.tram-marker.label-quiet')).toHaveCount(0);
});

test('scripted status is explicit and street labels never overlap markers or route labels', async ({
  page,
}) => {
  await page.goto('./?demo=health');
  await expect(page.locator('.demo-scenario-banner')).toBeVisible();
  await expect(page.locator('.demo-scenario-banner')).toHaveText(
    'Demo scenario — scripted incidents, not real service status',
  );
  await expect(
    page.locator('.condition-card .scripted-status-notice'),
  ).toHaveText('Demo scenario — scripted incidents, not real service status');
  await expect(
    page.locator('.sample-street-label').filter({ visible: true }).first(),
  ).toBeVisible();
  const overlappingNames = () =>
    page.evaluate(() => {
      const visible = (el: Element) =>
        getComputedStyle(el).visibility !== 'hidden' &&
        getComputedStyle(el).display !== 'none' &&
        getComputedStyle(el).opacity !== '0';
      const streets = [
        ...document.querySelectorAll('.sample-street-label'),
      ].filter(visible);
      const obstacles = [
        ...document.querySelectorAll(
          '.tram-marker, .development-marker, .tram-marker .marker-label',
        ),
      ].filter(visible);
      const overlap = (a: DOMRect, b: DOMRect) =>
        a.left < b.right - 1 &&
        a.right > b.left + 1 &&
        a.top < b.bottom - 1 &&
        a.bottom > b.top + 1;
      return streets
        .filter((street, index) =>
          [...obstacles, ...streets.slice(index + 1)].some((other) =>
            overlap(
              street.getBoundingClientRect(),
              other.getBoundingClientRect(),
            ),
          ),
        )
        .map((el) => el.textContent);
    });
  await expect.poll(overlappingNames).toEqual([]);
  await page.getByRole('button', { name: 'Zoom in', exact: true }).click();
  await page.getByRole('button', { name: 'Zoom in', exact: true }).click();
  await expect.poll(overlappingNames).toEqual([]);
});

test('mobile keeps the demo banner visible while credits and status remain usable', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('./?demo=health');
  await page.getByRole('button', { name: 'Sources & attribution' }).click();
  await expect(
    page.getByRole('dialog', { name: 'Sources and attribution' }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Close sources' }).click();
  await page.locator('.condition-card').scrollIntoViewIfNeeded();
  await expect(page.locator('.demo-scenario-banner')).toBeInViewport();
  await expect(
    page.locator('.condition-card .scripted-status-notice'),
  ).toBeInViewport();
});
