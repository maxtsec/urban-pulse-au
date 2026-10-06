import type { Page } from '@playwright/test';

export const scenarioPicker = (page: Page) =>
  page.getByRole('combobox', { name: 'Scenario' });

export async function chooseScenario(page: Page, label: string) {
  await scenarioPicker(page).selectOption({ label });
}

/** A timeline marker; markers at the same second carry every domain's label. */
export const moment = (page: Page, name: string) =>
  page
    .getByRole('group', { name: 'Scenario moments', exact: true })
    .getByRole('button', { name, exact: true });

export const detailsTab = (page: Page, name: string) =>
  page.getByRole('tab', { name: new RegExp(`^${name}`) });

export async function openTab(page: Page, name: string) {
  await detailsTab(page, name).click();
}

export const condition = (page: Page) =>
  page.getByTestId('condition').locator('strong');

/** Layer toggles live in a disclosure; open it before using a checkbox. */
export async function layer(page: Page, name: string) {
  const menu = page.locator('.layers-menu');
  if (!(await menu.evaluate((node: HTMLDetailsElement) => node.open)))
    await menu.locator(':scope > summary').click();
  return page.getByRole('checkbox', { name, exact: true });
}

export async function closeLayers(page: Page) {
  const menu = page.locator('.layers-menu');
  if (await menu.evaluate((node: HTMLDetailsElement) => node.open))
    await menu.locator(':scope > summary').click();
}
