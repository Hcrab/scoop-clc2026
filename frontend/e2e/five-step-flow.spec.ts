import { test, expect } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

test('five steps reuse the approved simulation while widgets change', async ({ page, request }) => {
  test.setTimeout(360_000);
  page.setDefaultTimeout(45_000);
  const endpoint = '/api/plans/P20260720';
  const out = path.resolve('..', 'reports', 'screenshots');
  await mkdir(out, { recursive: true });
  const record: any = { plan: 'P20260720', mocked_responses: false, screenshots: [], errors: [], simulation_requests: [] };
  const read = async (suffix = '') => {
    const r = await request.get(endpoint + suffix, { timeout: 120_000 });
    expect(r.ok(), await r.text()).toBeTruthy();
    return r.json();
  };
  const initial = await read();
  record.initial_simulation = { ...(await read('/simulation')), result: undefined };
  const dashboard = await read('/dashboard');
  const initialWidgets = dashboard.widgets.map((w: any) => w.id);
  const quantities = (d: any) => d.orders.map((o: any) => [o.sku, o.final_cases ?? Math.max(0, o.suggested_cases - o.capacity_cut_cases)])
    .sort((a: any, b: any) => a[0].localeCompare(b[0]));
  const steps = (name: string) => page.getByRole('tab', { name: new RegExp(`\\b${name}\\b`) })
    .or(page.getByRole('button', { name, exact: true }));
  const top = () => page.evaluate(() => window.scrollTo(0, 0));
  const take = async (name: string) => {
    await expect(page.locator('.inline-refresh')).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Settings', exact: true })).toBeEnabled();
    await top();
    const file = `n1-${name}.png`;
    await page.screenshot({ path: path.join(out, file), animations: 'disabled' });
    record.screenshots.push(`reports/screenshots/${file}`);
  };
  page.on('pageerror', e => record.errors.push(e.message));
  page.on('request', r => {
    if (r.method() === 'POST' && /\/(?:play|simulation)$/.test(new URL(r.url()).pathname))
      record.simulation_requests.push({ method: r.method(), url: r.url(), at: new Date().toISOString() });
  });
  const widgetEdits: number[] = [];
  let orderEdit: number | undefined;
  try {
    await page.goto('/');
    await steps('Report').click();
    await expect(page.locator('.generated-report iframe')).toBeVisible();
    await expect(page.frameLocator('.generated-report iframe').locator('figure[data-chart] svg').first()).toBeVisible();
    await expect(page.locator('.cohort-card').first()).toBeVisible();
    await expect(page.getByRole('button', { name: 'Review orders', exact: true })).toBeEnabled();
    await take('01-report');
    await page.getByRole('button', { name: 'Review orders', exact: true }).click();
    await expect(page.locator('.action-list')).toBeVisible();
    await expect(page.locator('.action-group tbody tr').first()).toBeVisible();
    await expect(page.getByRole('link', { name: 'Export orders', exact: true })).toHaveAttribute('href', `${endpoint}/orders.csv`);
    await take('02-orders');

    const approving = page.waitForResponse(r => r.url().endsWith('/approve-orders') && r.request().method() === 'POST');
    record.approval_clicked_at = new Date().toISOString();
    await page.getByRole('button', { name: 'Approve orders', exact: true }).click();
    const approved = await approving;
    expect(approved.ok(), await approved.text()).toBeTruthy();
    record.approval_finished_at = new Date().toISOString();
    await expect(page.getByRole('button', { name: 'Next: Play', exact: true })).toBeVisible();
    await expect(page.locator('.dashboard-widget')).toHaveCount(initialWidgets.length);

    await page.getByRole('button', { name: 'Add widget', exact: true }).click();
    const sheet = page.getByRole('dialog', { name: 'Add widget', exact: true });
    const title = 'Warehouse stock · Flow check';
    await sheet.getByLabel(/^Measure/).selectOption('on_hand');
    await sheet.getByLabel('Title', { exact: true }).fill(title);
    await expect(sheet.locator('.dashboard-preview strong')).toBeVisible();
    const adding = page.waitForResponse(r => r.url().endsWith('/dashboard') && r.request().method() === 'POST');
    await sheet.getByRole('button', { name: 'Add widget', exact: true }).click();
    const added = await adding;
    expect(added.ok(), await added.text()).toBeTruthy();
    const edit = await added.json(); widgetEdits.push(edit.edit_id);
    await expect(page.locator('.dashboard-widget').filter({ has: page.getByRole('heading', { name: title, exact: true }) })).toBeVisible();
    const addedWidget = page.locator('.dashboard-widget').filter({ has: page.getByRole('heading', { name: title, exact: true }) });
    await addedWidget.getByRole('button', { name: 'Edit', exact: true }).click();
    const editor = page.getByRole('dialog', { name: 'Edit widget', exact: true });
    await editor.getByLabel(/^Scope/).selectOption('sku:IC006');
    await editor.getByLabel('Title', { exact: true }).fill('Strawberry stock');
    const updating = page.waitForResponse(r => /\/dashboard\/[^/]+$/.test(r.url()) && r.request().method() === 'PUT');
    await editor.getByRole('button', { name: 'Save widget', exact: true }).click();
    const updated = await updating;
    expect(updated.ok(), await updated.text()).toBeTruthy();
    widgetEdits.push((await updated.json()).edit_id);
    const moving = page.waitForResponse(r => r.url().endsWith('/dashboard-layout') && r.request().method() === 'PUT');
    await page.getByRole('button', { name: 'Move Strawberry stock up', exact: true }).click();
    const moved = await moving;
    expect(moved.ok(), await moved.text()).toBeTruthy();
    widgetEdits.push((await moved.json()).edit_id);
    record.widget_edits = [...widgetEdits];
    await take('03-watch');
    expect(record.simulation_requests).toEqual([]);
    const ready = await read('/simulation');
    record.pre_play = { ...ready, result: undefined };
    expect(ready.status, JSON.stringify(record.pre_play)).toBe('ready');
    const flow = (await read()).flow;
    expect(ready.order_hash).toBe(flow.order_hash);
    record.play_entered_at = new Date().toISOString();
    expect(new Date(ready.completed_at).getTime()).toBeLessThanOrEqual(new Date(record.play_entered_at).getTime());
    await page.getByRole('button', { name: 'Next: Play', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Pause', exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: /^(?:1|2|4)×$/ })).toHaveCount(0);
    await expect(page.locator('.play .dashboard-widget')).toHaveCount(initialWidgets.length + 1);
    await page.getByRole('button', { name: 'Pause', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Resume', exact: true })).toBeVisible();
    await take('04-play');
    await page.getByRole('button', { name: 'Resume', exact: true }).click();
    await expect(page.getByRole('button', { name: 'See results', exact: true })).toBeVisible({ timeout: 100_000 });
    expect((await read()).flow.step).toBe('play');
    await page.getByRole('button', { name: 'See results', exact: true }).click();
    await expect(page.locator('.play-outcomes strong')).toHaveCount(3);
    await expect(page.locator('.dashboard-widget')).toHaveCount(initialWidgets.length + 1);
    await take('05-results');
    await page.getByText('See full comparison', { exact: true }).click();
    await expect(page.locator('.play-comparison table')).toBeVisible();
    const final = await read();
    expect(final.flow.step).toBe('results');
    expect(final.flow.max_step).toBe('results');
    expect(quantities(final)).toEqual(quantities(initial));
    record.result = { days: ready.result.days, summary: ready.result.summary, comparison: ready.result.affected_comparison };
    record.order_quantities_unchanged = true;

    await steps('Orders').click();
    const row = page.locator('.action-group tbody tr').first();
    const input = row.getByRole('spinbutton');
    const previous = Number(await input.inputValue());
    const boot = await (await request.get('/api/bootstrap')).json();
    const skuLabel = await row.locator('small').first().textContent();
    const product = boot.products.find((p: any) => skuLabel?.startsWith(p.sku));
    expect(product).toBeTruthy();
    const editing = page.waitForResponse(r => r.url().endsWith('/orders/bulk') && r.request().method() === 'POST');
    await input.fill(String(previous + Math.max(1, product.moq_cases)));
    await input.press('Enter');
    const edited = await editing;
    expect(edited.ok(), await edited.text()).toBeTruthy();
    orderEdit = (await edited.json()).edit_id;
    const changed = await read();
    expect(changed.flow.step).toBe('orders');
    expect(changed.flow.max_step).toBe('orders');
    expect(changed.flow.order_hash).not.toBe(ready.order_hash);
    expect(changed.flow.notice).toBeTruthy();
    await expect(page.getByText(changed.flow.notice, { exact: true })).toBeVisible();
    record.order_edit = { edit_id: orderEdit, old_hash: ready.order_hash, new_hash: changed.flow.order_hash,
      flow: changed.flow, simulation: { ...(await read('/simulation')), result: undefined } };
    expect(['queued', 'running', 'ready']).toContain(record.order_edit.simulation.status);
    const undoOrder = await request.post(`${endpoint}/edits/${orderEdit}/undo`);
    expect(undoOrder.ok(), await undoOrder.text()).toBeTruthy();
    orderEdit = undefined;
    expect(quantities(await read())).toEqual(quantities(initial));
    const reapproved = await request.post(`${endpoint}/approve-orders`);
    expect(reapproved.ok(), await reapproved.text()).toBeTruthy();
    record.order_edit.exact_undo = true;
    expect(record.simulation_requests).toEqual([]);
    expect(record.errors).toEqual([]);
    record.accepted = true;
  } finally {
    try {
      if (orderEdit != null) {
        const undo = await request.post(`${endpoint}/edits/${orderEdit}/undo`);
        expect(undo.ok(), await undo.text()).toBeTruthy();
      }
      for (const id of [...widgetEdits].reverse()) {
        const undo = await request.post(`${endpoint}/edits/${id}/undo`);
        expect(undo.ok(), await undo.text()).toBeTruthy();
      }
      expect((await read('/dashboard')).widgets.map((w: any) => w.id)).toEqual(initialWidgets);
      record.widget_exact_undo = true;
    } finally {
      await writeFile(path.resolve('..', 'reports', 'n1-flow.json'), JSON.stringify(record, null, 2) + '\n');
    }
  }
});
