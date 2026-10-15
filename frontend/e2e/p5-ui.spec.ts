import { test, expect } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

test('P5 screen typography, evidence access and shared Play dashboard', async ({ page, request }) => {
  test.setTimeout(900_000);
  page.setDefaultTimeout(60_000);
  const out = path.resolve('..', 'docs', 'screenshots');
  await mkdir(out, { recursive: true });
  const errors: string[] = [];
  page.on('pageerror', e => errors.push(e.message));
  const records: Record<string, unknown> = { mocked_responses: false, extra_llm_calls: false, screens: [] };
  const take = async (name: string) => {
    await page.screenshot({ path: path.join(out, `p5-${name}.png`) });
    (records.screens as string[]).push(`docs/screenshots/p5-${name}.png`);
  };
  const top = () => page.evaluate(() => window.scrollTo(0, 0));
  const settle = async () => {
    await expect(page.locator('.inline-refresh')).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Settings', exact: true })).toBeEnabled();
  };
  await page.goto('/');
  await page.getByRole('tab', { name: /Report & direction/ }).click();
  await expect(page.locator('.cohort-card').first()).toBeVisible();
  await settle();
  const font = await page.evaluate(() => ({
    body: getComputedStyle(document.body).fontSize,
    title: getComputedStyle(document.querySelector('h1')!).fontSize,
    tokens: Object.fromEntries(['page', 'section', 'key', 'body', 'label'].map(k => [k, getComputedStyle(document.documentElement).getPropertyValue(`--type-${k}`).trim()])),
  }));
  expect(font.body).toBe('15px');
  expect(font.title).toBe('32px');
  expect(font.tokens).toEqual({ page: '32px', section: '20px', key: '28px', body: '15px', label: '13px' });
  records.fonts = font;
  await top();
  await take('report');
  const frame = page.frameLocator('.generated-report iframe');
  await expect(frame.locator('figure[data-chart] svg').first()).toBeVisible();
  const evidence = frame.locator('button[data-evidence-id]').first();
  await evidence.click();
  await expect(frame.getByRole('region', { name: /^Evidence / }).first()).toBeVisible();
  await take('report-evidence');
  await top();
  await page.getByRole('tab', { name: /Orders/ }).click();
  await expect(page.locator('.action-group').first().locator('tbody tr')).toHaveCount(20);
  expect(await page.locator('.action-capacity').evaluate(el => getComputedStyle(el).position)).toBe('sticky');
  await settle();
  await top();
  await take('orders');
  const orderEvidence = page.locator('.action-group').first().locator('tbody tr').first().getByText('Order evidence', { exact: true });
  await orderEvidence.click();
  await expect(orderEvidence.locator('..').locator('p')).toBeVisible();
  await take('order-evidence');
  const approve = page.getByRole('button', { name: 'Approve orders', exact: true });
  await expect(approve).toBeEnabled();
  const response = page.waitForResponse(r => r.url().endsWith('/approve-orders') && r.request().method() === 'POST');
  await approve.click();
  expect((await response).ok()).toBeTruthy();
  await page.getByRole('button', { name: 'Dashboard', exact: true }).click();
  await expect(page.locator('.dashboard-widget').first()).toBeVisible();
  await settle();
  await top();
  await take('dashboard');
  const firstWidget = page.locator('.dashboard-widget').first();
  await expect(firstWidget.locator('.legend')).not.toContainText('Moving-average rule');
  await firstWidget.getByText('Source data', { exact: true }).click();
  await expect(firstWidget.locator('.dashboard-evidence tbody tr').first()).toBeVisible();
  await firstWidget.getByText('Source data', { exact: true }).click();
  const labelHeight = await firstWidget.locator('svg text').first().evaluate(el => el.getBoundingClientRect().height);
  expect(labelHeight).toBeGreaterThanOrEqual(10);
  records.dashboard_label_height = labelHeight;
  await page.getByRole('button', { name: 'Add widget', exact: true }).click();
  await expect(page.locator('.dashboard-preview strong')).toBeVisible();
  await take('widget-sheet');
  await page.getByRole('dialog').getByRole('button', { name: 'Cancel', exact: true }).click();
  await page.getByRole('button', { name: 'Play', exact: true }).click();
  await page.getByRole('button', { name: '4×', exact: true }).click();
  const runResponse = page.waitForResponse(r => r.url().endsWith('/play') && r.request().method() === 'POST', { timeout: 180_000 });
  await page.getByRole('button', { name: 'Play this order through', exact: true }).click();
  const played = await runResponse;
  expect(played.ok(), await played.text()).toBeTruthy();
  const result = await played.json();
  await expect(page.locator('.play-outcomes strong')).toHaveCount(3, { timeout: 90_000 });
  await page.locator('.play-comparison').scrollIntoViewIfNeeded();
  await take('play-result');
  await page.getByText('See full comparison', { exact: true }).click();
  await expect(page.locator('.play-comparison table').first()).toBeVisible();
  records.play = { days: result.days, affected_products: result.affected_skus.length, comparison: result.affected_comparison };
  for (const [navigation, name, target] of [
    ['Stores', 'stores', '.store-card'],
    ['Catalog', 'catalog', '.catalog-table tbody tr'],
    ['Evaluation', 'evaluation', '.page-heading h1'],
    ['Settings', 'settings', '.settings-panel'],
  ]) {
    await page.getByRole('button', { name: navigation, exact: true }).click();
    await expect(page.locator(target).first()).toBeVisible();
    await settle();
    if (navigation === 'Evaluation') await expect(page.getByRole('button', { name: 'Refresh', exact: true })).toBeEnabled();
    await top();
    await take(name);
    if (navigation === 'Stores') {
      await page.locator('.store-card').first().click();
      await expect(page.getByRole('dialog').locator('.chart svg')).toBeVisible();
      await take('store-details');
      await page.getByRole('button', { name: 'Close dialog', exact: true }).click();
    }
    if (navigation === 'Catalog') {
      await page.locator('.catalog-table .product-cell').first().click();
      await expect(page.getByRole('dialog').locator('.nutrition')).toBeVisible();
      await take('product-details');
      await page.getByRole('button', { name: 'Close dialog', exact: true }).click();
    }
  }
  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('button', { name: /^Plans/ }).click();
  await page.getByRole('tab', { name: /Report & direction/ }).click();
  await expect(page.locator('.cohort-card').first()).toBeVisible();
  await page.getByRole('button', { name: /Show discussion/ }).click();
  await expect(page.getByRole('textbox', { name: 'Discuss this plan', exact: true })).toBeVisible();
  await top();
  await take('discussion');
  await page.setViewportSize({ width: 960, height: 1000 });
  await top();
  await take('narrow');
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(962);
  const bootstrap = await request.get('/api/bootstrap');
  expect(bootstrap.ok()).toBeTruthy();
  records.page_errors = errors;
  expect(errors).toEqual([]);
  await writeFile(path.resolve('..', 'reports', 'p5-ui-acceptance.json'), JSON.stringify(records, null, 2) + '\n');
});
