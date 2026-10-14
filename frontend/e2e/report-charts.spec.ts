import { test, expect } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import path from 'node:path';

test('report figures and expanded trends use the saved evidence series', async ({page})=>{
  // This is a renderer fixture, not a generated report or algorithm acceptance run.
  await page.route('**/api/plans/*',async route=>{
    const url=new URL(route.request().url());
    if(!/^\/api\/plans\/[^/]+$/.test(url.pathname)||route.request().method()!=='GET')return route.continue();
    const response=await route.fetch();const detail=await response.json();
    detail.plan.stage='discover';
    detail.review={status:'complete',report:'Renderer fixture',questions:[],claims:[],
      presentation:{title:'Chart renderer fixture',css:'article{padding:24px}h3{font-size:20px}figure{margin:16px 0}',
        html:'<svg data-model-drawn="true"><path d="M0 0L100 100"/></svg><article data-report-card><h3>Fixture requests versus expected</h3><button data-trend-id="Q1" aria-label="Expand trend">Expand trend</button><figure data-chart="line" data-evidence-id="Q1" data-series="actual,expected"><figcaption>Saved daily requests</figcaption></figure><button data-evidence-id="Q1" aria-label="View query">View query</button></article>'},
      queries:[{id:'Q1',name:'query_group',args:{group_ids:['fixture']},result:{daily:Array.from({length:28},(_,i)=>({date:`2026-06-${String(i+1).padStart(2,'0')}`,requested_units:100+i*2,expected_units:100}))}}]};
    await route.fulfill({response,json:detail});
  });
  await page.goto('/');
  const frame=page.frameLocator('iframe[title="Chart renderer fixture"]');
  await expect(frame.getByRole('img',{name:/Actual: 154/})).toBeVisible();
  await expect(frame.locator('svg[data-model-drawn]')).toHaveCount(0);
  await expect(frame.locator('figure')).not.toHaveAttribute('role','button');
  await frame.getByRole('button',{name:'28 days',exact:true}).click();
  await expect(frame.locator('figure .chart-summary')).toContainText('1 Jun');
  await frame.getByRole('button',{name:'Expand trend',exact:true}).click();
  await expect(frame.getByRole('region',{name:'query group daily trend'})).toBeVisible();
  await expect(frame.getByRole('region').getByRole('img')).toHaveAttribute('aria-label',/Actual: 154/);
  await frame.getByRole('button',{name:'Collapse trend',exact:true}).click();
  await frame.getByRole('button',{name:'View query',exact:true}).click();
  await expect(frame.getByRole('region',{name:'Evidence Q1'})).toContainText('fixture');
  const out=path.resolve('..','docs','screenshots');await mkdir(out,{recursive:true});
  await expect(page.getByText('Loading changes…',{exact:true})).toHaveCount(0,{timeout:60000});
  await expect(frame.getByRole('img',{name:/Actual: 154/}).first()).toBeVisible();
  await page.locator('iframe').scrollIntoViewIfNeeded();
  await page.screenshot({path:path.join(out,'report-chart-renderer-fixture.png')});
});
