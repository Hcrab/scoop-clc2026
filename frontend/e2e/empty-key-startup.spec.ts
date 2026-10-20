import { test, expect } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { offlineASGI } from './support/offline-asgi';

test('empty-key app serves the real offline report and orders', async ({ page }) => {
  test.setTimeout(300_000);
  const bridge=offlineASGI();
  try {
    await bridge.attach(page);
    const health=await (await bridge.request.get('/health')).json();
    expect(health.provider).toBe('scripted');expect(health.live).toBe(false);
    const boot=await (await bridge.request.get('/api/bootstrap')).json();
    expect(boot.today).toBe('2026-07-20');expect(boot.products).toHaveLength(75);
    await page.goto('/');
    await page.getByRole('tab',{name:/Report & direction/}).click();
    await expect(page.locator('.cohort-card')).toHaveCount(5);
    const frame=page.frameLocator('.generated-report iframe');
    await expect(frame.locator('article[data-report-card]')).toHaveCount(5);
    await expect(frame.locator('svg')).toHaveCount(0);
    await expect(page.getByText('The evidence-grounded report could not be completed.',{exact:true})).toHaveCount(0);
    const out=path.resolve('..','reports','screenshots');await mkdir(out,{recursive:true});
    await page.screenshot({path:path.join(out,'p7-empty-key-report.png')});
    const report=await (await bridge.request.get('/api/plans/P20260720')).json();
    expect(report.review.status).toBe('offline');expect(report.orders).toHaveLength(75);
    expect((await bridge.request.get('/api/plans/P20260720/order-summary')).ok()).toBe(true);
    await writeFile(path.resolve('..','reports','p7-empty-key-browser.json'),JSON.stringify({
      transport:'Real FastAPI TestClient over stdio; no fabricated responses or TCP listener',
      key_empty:true,provider:health.provider,week:boot.today,products:75,cohort_cards:5,
      report_articles:5,model_svg:0,order_rows:75,screenshot:'reports/screenshots/p7-empty-key-report.png'
    },null,2)+'\n');
  } finally {
    await page.unrouteAll({behavior:'ignoreErrors'});bridge.close();
  }
});
