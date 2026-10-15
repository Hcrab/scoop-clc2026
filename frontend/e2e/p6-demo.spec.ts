import { test, expect } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

test('P6 single world, default week and actual quiet-week round trip', async ({ page, request }) => {
  test.setTimeout(600_000);
  page.setDefaultTimeout(90_000);
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  const out=path.resolve('..','docs','screenshots');await mkdir(out,{recursive:true});
  const json=async (url:string)=>{const r=await request.get(url,{timeout:90_000});expect(r.ok(),await r.text()).toBeTruthy();return r.json()};
  const before=await json('/api/demo-settings');
  expect(before.scenario_id).toBe('fresh-week');expect(before.week_start).toBe('2026-07-20');
  expect((await json('/api/bootstrap')).node.capacity_pallets).toBe(71);
  await page.goto('/');
  await expect(page.getByRole('tab',{name:/Report & direction/})).toHaveAttribute('aria-selected','true');
  await expect(page.locator('.cohort-card').first()).toContainText('Water-based');
  await expect(page.locator('.cohort-card')).toHaveCount(5);
  await page.screenshot({path:path.join(out,'p6-default-report.png')});
  await page.evaluate(()=>window.scrollTo(0,0));
  await page.getByRole('button',{name:'Settings',exact:true}).click();
  await expect(page.locator('.scenario-card')).toHaveCount(0);
  for(const old of ['Summer trading','Another summer','Crosscurrents','New season','Fresh week'])await expect(page.getByText(old,{exact:true})).toHaveCount(0);
  await expect(page.getByRole('combobox',{name:'Week starting',exact:true})).toHaveValue('2026-07-20');
  await page.screenshot({path:path.join(out,'p6-settings.png')});
  await page.getByRole('combobox',{name:'Week starting',exact:true}).selectOption('2026-06-22');
  const switched=page.waitForResponse(r=>r.url().endsWith('/api/demo-settings/select')&&r.request().method()==='POST',{timeout:180_000});
  await page.getByRole('button',{name:'Apply',exact:true}).click();expect((await switched).ok()).toBeTruthy();
  await expect(page.locator('.cohort-card')).toHaveCount(0);
  await expect(page.getByText('No demand changes to review this week.',{exact:true})).toBeVisible();
  const quiet=await json('/api/plans/P20260622/cohorts');expect(quiet.cards).toEqual([]);
  await page.screenshot({path:path.join(out,'p6-quiet-week.png')});
  await page.evaluate(()=>window.scrollTo(0,0));
  await page.getByRole('button',{name:'Settings',exact:true}).click();
  await page.getByRole('combobox',{name:'Week starting',exact:true}).selectOption('2026-07-20');
  const restored=page.waitForResponse(r=>r.url().endsWith('/api/demo-settings/select')&&r.request().method()==='POST',{timeout:180_000});
  await page.getByRole('button',{name:'Apply',exact:true}).click();expect((await restored).ok()).toBeTruthy();
  await expect(page.locator('.cohort-card')).toHaveCount(5);
  await expect(page.locator('.cohort-card').first()).toContainText('Water-based');
  expect(errors).toEqual([]);
  await writeFile(path.resolve('..','reports','p6-browser-acceptance.json'),JSON.stringify({mocked_responses:false,extra_llm_calls:false,
    default_week:'2026-07-20',capacity:71,quiet_week:'2026-06-22',quiet_cards:0,restored_cards:5,
    first_card:'Water-based (25 SKUs; not isolated strawberry)',world_switcher_removed:true,errors},null,2)+'\n');
});
