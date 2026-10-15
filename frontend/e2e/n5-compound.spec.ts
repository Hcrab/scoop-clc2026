import { test, expect } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

test('Compound path, shared evidence drilldown and same-cold-store outcome', async ({page,request})=>{
  test.setTimeout(600_000);
  page.setDefaultTimeout(30_000);
  const endpoint='/api/plans/P20260727',out=path.resolve('..','docs','screenshots');
  await mkdir(out,{recursive:true});
  const record:any={mocked_responses:false,errors:[],screenshots:[]};
  page.on('pageerror',error=>record.errors.push(error.message));
  const read=async(suffix='')=>{const r=await request.get(endpoint+suffix,{timeout:120_000});expect(r.ok(),await r.text()).toBeTruthy();return r.json()};
  const shot=async(name:string)=>{const file=`n5-${name}.png`;await page.screenshot({path:path.join(out,file),animations:'disabled'});record.screenshots.push(`docs/screenshots/${file}`)};
  const top=async()=>{await page.evaluate(()=>window.scrollTo(0,0));await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))))};
  const before=await read(),card=before.cohort_cards[0];
  expect(before.review.status).toBe('complete');
  expect(before.review.model).toBe('gemini-3.8-flash');
  expect(before.review.presentation.html).not.toMatch(/<svg\b/i);
  expect([...card.skus].sort()).toEqual(['IC006','IC061','IC062','IC063']);
  expect(card.tag_path.filter((p:any)=>p.included).map((p:any)=>p.id).sort()).toEqual(['band:dairy:0','band:price_hkd:0','flavour:strawberry'].sort());
  record.card={id:card.id,name:card.name,effect_pct:card.effect_pct,drilldown:card.drilldown.steps.map((s:any)=>({label:s.label,effect:s.effect_pct,rest:s.rest_effect_pct}))};
  await request.put(endpoint+'/flow',{data:{step:'report'}});
  await page.goto('/');
  await expect(page.frameLocator('.generated-report iframe').locator('figure[data-card="cohort"]').first()).toHaveAttribute('data-id',card.id);
  const side=page.getByRole('complementary',{name:'Demand changes and context'}).locator('.cohort-card').first();
  await expect(side).toContainText(card.name);
  await expect(side.locator('.cohort-path span')).toHaveCount(card.tag_path.length);
  await side.scrollIntoViewIfNeeded();await shot('01-collapsed-card');
  await side.getByText('How we found it',{exact:true}).click();
  const drill=side.locator('.cohort-drilldown');
  await expect(drill.locator('.drill-row')).toHaveCount(card.tag_path.length+1);
  const firstChart=await drill.locator('svg').innerHTML();
  await drill.locator('.drill-row').last().click();
  await expect(drill.locator('.drill-chart-head strong')).toContainText(card.drilldown.steps.at(-1).label);
  expect(await drill.locator('svg').innerHTML()).not.toBe(firstChart);
  await drill.getByRole('combobox').selectOption('70');
  await side.scrollIntoViewIfNeeded();await shot('02-strawberry-drilldown');
  await page.goto(`/plans/P20260727/evidence/Q-cohort-${card.id}`);
  const modal=page.getByRole('dialog');
  await expect(modal.locator('.cohort-drilldown')).toBeVisible();
  await modal.locator('.drill-row').last().click();
  await expect(modal.locator('.drill-chart-head strong')).toContainText(card.drilldown.steps.at(-1).label);
  await shot('03-evidence-drilldown');
  await modal.getByRole('button',{name:'Close evidence',exact:true}).click();
  await top();
  if((await read()).plan.stage==='discover'){
    await page.getByRole('button',{name:'Review orders',exact:true}).click();
  }else{
    await page.getByRole('tab',{name:/\bOrders\b/}).click();
  }
  await expect(page.getByRole('button',{name:'Approve orders',exact:true})).toBeVisible();
  await top();await page.getByRole('button',{name:'Approve orders',exact:true}).click();
  await expect(page.getByRole('tab',{name:/\bWatch\b/})).toHaveAttribute('aria-selected','true');
  await expect.poll(async()=>(await read('/simulation')).status,{timeout:300_000,intervals:[2000]}).toBe('ready');
  const ready=await read('/simulation'),result=ready.result;
  expect(result).not.toHaveProperty('matched');
  for(const policy of ['scoop','baseline']){
    expect(result.summary[policy].peak_pallets).toBeLessThanOrEqual(result.capacity_pallets+1e-8);
    expect(result.summary[policy].days_over_capacity).toBe(0);
  }
  record.simulation={order_hash:ready.order_hash,elapsed_seconds:ready.elapsed_seconds,summary:result.summary};
  await page.getByRole('button',{name:'Next: Play',exact:true}).click();
  await expect(page.getByRole('button',{name:'See results',exact:true})).toBeVisible({timeout:90_000});
  await page.getByRole('button',{name:'See results',exact:true}).click();
  await expect(page.locator('.play-outcomes strong')).toHaveCount(3);
  await expect(page.locator('.results-cold-store')).toContainText('Same cold store');
  await top();await shot('04-same-store-results');
  await page.getByText('See full comparison',{exact:true}).click();
  await expect(page.locator('.play-comparison table')).toHaveCount(1);
  await page.locator('.play-comparison').scrollIntoViewIfNeeded();await shot('05-full-comparison');
  expect(record.errors).toEqual([]);
  await writeFile(path.resolve('..','reports','n5-browser.json'),JSON.stringify(record,null,2)+'\n');
  const differences=['lost_units','stockout_sku_days','lost_margin'].map(key=>result.summary.baseline[key]-result.summary.scoop[key]);
  await expect(page.locator('.play-outcomes .result-negative')).toHaveCount(differences.filter(value=>value<0).length);
});
