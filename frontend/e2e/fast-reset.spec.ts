import { test, expect } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

test('Settings reset restores the prepared week without rebuilding its report', async ({page,request})=>{
  test.setTimeout(120_000);
  const endpoint='/api/plans/P20260727';
  const errors:string[]=[],resetTimes:number[]=[];
  const evidence:any={mocked_responses:false,errors,reset_api_ms:resetTimes};
  page.on('pageerror',error=>errors.push(error.message));
  const read=async()=>{const response=await request.get(endpoint);expect(response.ok(),await response.text()).toBeTruthy();return response.json()};
  const initial=await read();
  expect(initial.plan.stage).toBe('discover');
  expect(initial.review.status).toBe('complete');
  const originalWidgets=initial.dashboard.widgets.map(({id,title,metric,scope,threshold}:any)=>({id,title,metric,scope,threshold}));
  const cases=(detail:any)=>detail.orders.map((row:any)=>[row.sku,row.final_cases??Math.max(0,row.suggested_cases-row.capacity_cut_cases)]).sort((a:any,b:any)=>a[0].localeCompare(b[0]));
  let modified=false,restored=false;
  try{
    const added=await request.post(endpoint+'/dashboard',{data:{title:'Reset verification stock',metric:'on_hand',scope:{kind:'sku',key:'IC006'}}});
    expect(added.ok(),await added.text()).toBeTruthy();modified=true;
    await page.goto('/');
    await page.getByRole('button',{name:'Review orders',exact:true}).click();
    const row=page.locator('.action-group tbody tr').first(),input=row.getByRole('spinbutton');
    const original=Number(await input.inputValue());
    const edited=page.waitForResponse(response=>response.url().endsWith('/orders/bulk')&&response.request().method()==='POST');
    await input.fill(String(Math.max(0,original-1)));await input.press('Enter');
    expect((await edited).ok()).toBeTruthy();
    await expect.poll(async()=>JSON.stringify(cases(await read()))).not.toBe(JSON.stringify(cases(initial)));
    await expect(page.locator('.inline-refresh')).toHaveCount(0);
    await expect(page.getByRole('button',{name:'Settings',exact:true})).toBeEnabled();
    await page.getByRole('button',{name:'Settings',exact:true}).click();
    await expect(page.getByRole('heading',{name:'Settings',exact:true})).toBeVisible();
    await page.evaluate(()=>window.scrollTo(0,0));
    await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
    await page.getByRole('button',{name:'Reset simulation',exact:true}).click();
    const modal=page.getByRole('dialog',{name:'Reset this simulation?',exact:true});
    const responsePromise=page.waitForResponse(response=>response.url().endsWith('/demo-settings/reset')&&response.request().method()==='POST');
    const started=performance.now();
    await modal.getByRole('button',{name:'Reset simulation',exact:true}).click();
    const response=await responsePromise;
    await response.finished();
    const timing=response.request().timing();
    resetTimes.push(Math.round(timing.responseEnd-timing.requestStart));
    evidence.click_to_response_ms=Math.round(performance.now()-started);
    expect(response.ok(),await response.text()).toBeTruthy();
    restored=true;
    await expect(page.getByRole('tab',{name:/\bReport\b/})).toHaveAttribute('aria-selected','true');
    await expect(page.locator('.cohort-card')).toHaveCount(initial.cohort_cards.length);
    await expect(page.frameLocator('.generated-report iframe').locator('figure[data-chart] svg').first()).toBeVisible();
    evidence.ready_ui_ms=Math.round(performance.now()-started);
    const final=await read();
    expect(cases(final)).toEqual(cases(initial));
    expect(final.review).toEqual(initial.review);
    expect(final.cohort_cards).toEqual(initial.cohort_cards);
    expect(final.dashboard.widgets.map(({id,title,metric,scope,threshold}:any)=>({id,title,metric,scope,threshold}))).toEqual(originalWidgets);
    expect(final.messages).toEqual([]);expect(final.decisions).toEqual([]);
    expect(final.plan.stage).toBe('discover');expect(final.plan.locked_at).toBeNull();
    expect(final.flow.step).toBe('report');expect(final.flow.max_step).toBe('report');
    const settings=await(await request.get('/api/demo-settings')).json();
    for(let n=0;n<2;n++){
      const repeatStarted=performance.now();
      const repeat=await request.post('/api/demo-settings/reset',{data:{scenario_id:settings.scenario_id,week_start:'2026-07-27'}});
      resetTimes.push(Math.round(performance.now()-repeatStarted));expect(repeat.ok(),await repeat.text()).toBeTruthy();
      expect(cases(await read())).toEqual(cases(initial));
    }
    await page.reload();
    await expect(page.getByRole('tab',{name:/\bReport\b/})).toHaveAttribute('aria-selected','true');
    await expect(page.locator('.cohort-card')).toHaveCount(initial.cohort_cards.length);
    await expect.poll(()=>page.locator('.cohort-card .product-icon img').evaluateAll(nodes=>nodes.every(img=>(img as HTMLImageElement).complete&&(img as HTMLImageElement).naturalWidth===256))).toBeTruthy();
    await mkdir(path.resolve('..','docs','screenshots'),{recursive:true});
    await page.screenshot({path:path.resolve('..','docs','screenshots','fast-reset-report.png'),animations:'disabled'});
    expect(errors).toEqual([]);
    expect(Math.max(...resetTimes)).toBeLessThan(2_000);
    expect(evidence.ready_ui_ms).toBeLessThan(5_000);
    evidence.restored={orders:final.orders.length,widgets:originalWidgets.length,report_identical:true,cards_identical:true,flow:final.flow.step,decisions:0,messages:0};
  }finally{
    if(modified&&!restored){
      const settings=await(await request.get('/api/demo-settings')).json();
      await request.post('/api/demo-settings/reset',{data:{scenario_id:settings.scenario_id,week_start:'2026-07-27'}});
    }
    await writeFile(path.resolve('..','reports','fast-reset-browser.json'),JSON.stringify(evidence,null,2)+'\n');
  }
});
