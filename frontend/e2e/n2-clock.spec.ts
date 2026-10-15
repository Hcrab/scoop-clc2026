import { test, expect } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

test('N2 ten-minute clock, timed events, stock gauge and final frame', async ({ page, request }) => {
  test.setTimeout(300_000);
  page.setDefaultTimeout(45_000);
  const endpoint = '/api/plans/P20260720';
  const out = path.resolve('..', 'docs', 'screenshots');
  await mkdir(out, { recursive: true });
  const record: any = { plan: 'P20260720', mocked_responses: false, screenshots: [], errors: [] };
  const read = async (suffix = '') => {
    const response = await request.get(endpoint + suffix, { timeout: 120_000 });
    expect(response.ok(), await response.text()).toBeTruthy();
    return response.json();
  };
  const quantities = (data: any) => data.orders.map((o: any) => [o.sku, o.effective_cases])
    .sort((a: any, b: any) => a[0].localeCompare(b[0]));
  const initial = await read();
  page.on('pageerror', e => record.errors.push(e.message));
  const shot = async (name: string) => {
    await page.evaluate(() => window.scrollTo(0, 0));
    const file = `n2-${name}.png`;
    await page.screenshot({ path: path.join(out, file), animations: 'disabled' });
    record.screenshots.push(`docs/screenshots/${file}`);
  };
  try {
    await page.goto('/');
    await page.getByRole('tab', { name: /\bOrders\b/ }).click();
    await expect(page.locator('.action-group tbody tr').first()).toBeVisible();
    const approving = page.waitForResponse(r => r.url().endsWith('/approve-orders') && r.request().method() === 'POST');
    await page.getByRole('button', { name: 'Approve orders', exact: true }).click();
    expect((await approving).ok()).toBeTruthy();
    // N1 tests the complete preparation flow. This test waits for the new timed
    // payload so that its assertions measure playback rather than preparation.
    let prepared: any;
    await expect.poll(async () => { prepared = await read('/simulation'); return prepared.status; },
      { timeout: 180_000, intervals: [1500] }).toBe('ready');
    expect(prepared.result.intraday.step_minutes).toBe(10);
    expect(prepared.result.runs.scoop.hourly.on_hand.length).toBe(prepared.result.days * 24);
    record.simulation = { ...prepared, result: undefined };
    const result = prepared.result, profile = result.intraday;
    let balances = 0, maxError = 0;
    const equal = (actual: number, expected: number) => {
      maxError = Math.max(maxError, Math.abs(actual - expected));
      balances++;
    };
    for (const policy of ['scoop', 'baseline']) {
      const { per_sku: per, hourly } = result.runs[policy];
      for (let d = 0; d < result.days; d++) for (let j = 0; j < result.skus.length; j++) {
        const opening = d ? per.on_hand[d - 1][j] : profile.opening_on_hand[j];
        for (const key of ['demand', 'shipped', 'lost', 'arrived'])
          equal(hourly[key].slice(d * 24, d * 24 + 24).reduce((total: number, row: number[]) => total + row[j], 0), per[key][d][j]);
        equal(hourly.on_hand_delta.slice(d * 24, d * 24 + 24).reduce((total: number, row: number[]) => total + row[j], 0), per.on_hand[d][j] - opening);
        for (let h = 0; h < 24; h++) {
          const at = d * 24 + h, before = h ? hourly.on_hand[at - 1][j] : opening;
          equal(hourly.on_hand[at][j], before + hourly.arrived[at][j] - hourly.shipped[at][j]);
          equal(hourly.on_hand_delta[at][j], hourly.on_hand[at][j] - before);
        }
        equal(hourly.on_hand[d * 24 + 23][j], per.on_hand[d][j]);
      }
    }
    expect(maxError).toBeLessThan(1e-8);
    const shortages = result.events.filter((event: any) => ['stockout', 'kept'].includes(event.kind));
    expect(shortages.length).toBeGreaterThan(0);
    for (const event of shortages) {
      const d = result.dates.indexOf(event.date), j = result.skus.indexOf(event.sku);
      const per = result.runs[event.kind === 'stockout' ? 'scoop' : 'baseline'].per_sku;
      const opening = d ? per.on_hand[d - 1][j] : profile.opening_on_hand[j];
      const first = profile.minutes.find((minute: number, k: number) => minute < 1440 &&
        per.demand[d][j] * profile.demand_cdf[k] > opening + (minute >= profile.arrival_minutes[d][j] ? per.arrived[d][j] : 0) + 1e-9);
      expect(event.minute).toBe(first);
    }
    record.conservation = { policies: 2, products: result.skus.length, days: result.days, balances, max_error: maxError, timed_shortages: shortages.length };
    await expect(page.locator('.inline-refresh')).toHaveCount(0);
    await page.getByRole('button', { name: 'Next: Play', exact: true }).click();
    const clock = page.locator('.play-clock');
    await expect(page.getByRole('button', { name: 'Pause', exact: true }).or(page.getByRole('button', { name: 'Replay', exact: true }))).toBeVisible();
    if (await page.getByRole('button', { name: 'Replay', exact: true }).isVisible())
      await page.getByRole('button', { name: 'Replay', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Pause', exact: true })).toBeVisible();
    await expect(clock.locator('strong')).toContainText(/\d{2}:\d{2}/);
    await expect.poll(async () => Number(await clock.getAttribute('data-minute')),
      { timeout: 30_000, intervals: [20] }).toBeGreaterThanOrEqual(12 * 60);
    await page.getByRole('button', { name: 'Pause', exact: true }).click();
    const minute = Number(await clock.getAttribute('data-minute'));
    expect(Number.isFinite(minute)).toBeTruthy();
    expect(minute % 10).toBe(0);
    expect(minute).toBeLessThanOrEqual(19 * 60);
    const paused = await clock.locator('strong').textContent();
    await page.waitForTimeout(120);
    expect(await clock.locator('strong').textContent()).toBe(paused);
    const events = page.locator('.play-event');
    expect(await events.count()).toBeGreaterThan(0);
    await expect(events.first().locator('span').first()).toContainText(/\d{2}:\d{2}/);
    await expect(page.locator('.play-capacity')).toBeVisible();
    record.midday = { minute, clock: paused, events: await events.allTextContents(),
      gauge: await page.locator('.play-capacity').textContent() };
    await shot('01-midday');
    const resumedAt = Date.now();
    const expectedReplayMs = (result.days * 144 - 1 - minute / 10) * 2000 / 144;
    await page.getByRole('button', { name: 'Resume', exact: true }).click();
    await expect.poll(async () => clock.locator('strong').textContent(), { timeout: 5000, intervals: [20] }).not.toBe(paused);
    await expect(page.getByRole('button', { name: 'See results', exact: true })).toBeVisible({ timeout: 100_000 });
    await expect(page.getByRole('button', { name: 'See results', exact: true })).toBeEnabled();
    record.playback = { expected_remaining_ms: expectedReplayMs, actual_remaining_ms: Date.now() - resumedAt };
    expect(record.playback.actual_remaining_ms).toBeGreaterThan(expectedReplayMs * .8);
    expect(record.playback.actual_remaining_ms).toBeLessThan(expectedReplayMs * 1.3 + 1000);
    const final = await read();
    expect(final.flow.step).toBe('play');
    expect(final.flow.max_step).toBe('results');
    expect(quantities(final)).toEqual(quantities(initial));
    record.final_clock = await clock.locator('strong').textContent();
    await shot('02-final-frame');
    await page.getByRole('button', { name: 'See results', exact: true }).click();
    await expect(page.locator('.play-outcomes strong')).toHaveCount(3);
    await expect(page.locator('.dashboard-widget')).toHaveCount(5);
    await shot('03-results');
    expect(record.errors).toEqual([]);
    record.accepted = true;
  } finally {
    await writeFile(path.resolve('..', 'reports', 'n2-clock.json'), JSON.stringify(record, null, 2) + '\n');
  }
});
