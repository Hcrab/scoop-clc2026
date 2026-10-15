import { test, expect } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

test('N6 real report → orders → watch → timed Play → measured Results', async ({page,request})=>{
  test.setTimeout(420_000);
  page.setDefaultTimeout(45_000);
  const endpoint='/api/plans/P20260727',out=path.resolve('..','docs','screenshots');
  await mkdir(out,{recursive:true});
  const record:any={mocked_responses:false,plan:'P20260727',screenshots:[],errors:[],simulation_requests:[]};
  const edits:number[]=[];
  let watchEdits=false;
  page.on('pageerror',error=>record.errors.push(error.message));
  page.on('request',req=>{if(watchEdits&&req.method()==='POST'&&/\/(play|simulation)$/.test(new URL(req.url()).pathname))record.simulation_requests.push(req.url())});
  const read=async(suffix='')=>{const response=await request.get(endpoint+suffix,{timeout:120_000});expect(response.ok(),await response.text()).toBeTruthy();return response.json()};
  const top=async()=>{await page.evaluate(()=>window.scrollTo(0,0));await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))))};
  const shot=async(name:string)=>{
    await expect(page.locator('.inline-refresh')).toHaveCount(0);
    await expect.poll(()=>page.locator('.product-icon img').evaluateAll(nodes=>nodes.every(img=>(img as HTMLImageElement).complete&&(img as HTMLImageElement).naturalWidth===256))).toBeTruthy();
    await top();const file=`n6-${name}.png`;await page.screenshot({path:path.join(out,file),animations:'disabled'});record.screenshots.push(`docs/screenshots/${file}`)
  };
  const quantities=(detail:any)=>detail.orders.map((o:any)=>[o.sku,o.final_cases??Math.max(0,o.suggested_cases-o.capacity_cut_cases)]).sort((a:any,b:any)=>a[0].localeCompare(b[0]));
  const widgetState=(dashboard:any)=>dashboard.widgets.map(({id,title,metric,scope,position,threshold}:any)=>({id,title,metric,scope,position,threshold}));
  const initial=await read(),dashboard=await read('/dashboard');
  const initialWidgets=widgetState(dashboard);
  record.initial={stage:initial.plan.stage,quantities:quantities(initial),widgets:initialWidgets};
  expect(initial.review.status).toBe('complete');
  expect(initial.review.model).toBe('gemini-3.8-flash');
  expect(initial.review.presentation.html).not.toMatch(/<svg\b/i);
  try{
    const reset=await request.put(endpoint+'/flow',{data:{step:'report'}});expect(reset.ok()).toBeTruthy();
    await page.goto('/');
    await expect(page.getByRole('tab')).toHaveCount(5);
    await expect(page.getByRole('tab',{name:/\bReport\b/})).toHaveAttribute('aria-selected','true');
    const frame=page.frameLocator('.generated-report iframe');
    await expect(frame.locator('figure[data-chart] svg').first()).toBeVisible();
    await expect(frame.locator('figure[data-card="cohort"]').first()).toHaveAttribute('data-id',initial.cohort_cards[0].id);
    await expect(page.locator('.cohort-card')).toHaveCount(initial.cohort_cards.length);
    await expect(page.locator('.cohort-card').first()).toBeVisible();
    await expect(page.getByText('Loading changes…',{exact:true})).toHaveCount(0);
    await shot('01-report');
    record.report={model:initial.review.model,title:initial.review.presentation.title,first_card:initial.cohort_cards[0].name};

    await page.getByRole('button',{name:'Review orders',exact:true}).click();
    await expect(page.getByRole('tab',{name:/\bOrders\b/})).toHaveAttribute('aria-selected','true');
    await expect(page.locator('.action-group tbody tr').first()).toBeVisible();
    await expect(page.getByRole('link',{name:'Export orders',exact:true})).toHaveAttribute('href',`${endpoint}/orders.csv`);
    expect(await page.locator('.action-capacity').evaluate(el=>getComputedStyle(el).position)).toBe('sticky');
    await expect(page.locator('.action-group').first().locator('.product-icon img').first()).toBeVisible();
    await shot('02-orders');
    const approval=page.waitForResponse(response=>response.url().endsWith('/approve-orders')&&response.request().method()==='POST');
    await top();await page.getByRole('button',{name:'Approve orders',exact:true}).click();
    expect((await approval).ok()).toBeTruthy();
    await expect(page.getByRole('tab',{name:/\bWatch\b/})).toHaveAttribute('aria-selected','true');
    await expect.poll(async()=>(await read('/simulation')).status,{timeout:240_000,intervals:[2000]}).toBe('ready');
    const prepared=await read('/simulation');
    record.preparation={status:prepared.status,order_hash:prepared.order_hash,completed_at:prepared.completed_at,elapsed_seconds:prepared.elapsed_seconds};

    watchEdits=true;
    await page.getByRole('button',{name:'Add widget',exact:true}).click();
    const sheet=page.getByRole('dialog',{name:'Add widget',exact:true});
    await sheet.getByLabel(/^Scope/).selectOption('sku:IC006');
    await sheet.getByLabel(/^Measure/).selectOption('on_hand');
    await sheet.getByLabel('Title',{exact:true}).fill('Strawberry Burst Bar stock');
    await expect(sheet.locator('.dashboard-preview strong')).toBeVisible();
    const adding=page.waitForResponse(response=>response.url().endsWith('/dashboard')&&response.request().method()==='POST');
    await sheet.getByRole('button',{name:'Add widget',exact:true}).click();
    const added=await adding;expect(added.ok()).toBeTruthy();edits.push((await added.json()).edit_id);
    await expect(page.locator('.dashboard-widget')).toHaveCount(initialWidgets.length+1);
    expect(record.simulation_requests).toEqual([]);
    const afterWidget=await read('/simulation');
    expect(afterWidget.order_hash).toBe(prepared.order_hash);
    expect(afterWidget.completed_at).toBe(prepared.completed_at);
    await shot('03-watch');watchEdits=false;

    record.play_entered_at=new Date().toISOString();
    expect(new Date(prepared.completed_at).getTime()).toBeLessThanOrEqual(new Date(record.play_entered_at).getTime());
    await page.getByRole('button',{name:'Next: Play',exact:true}).click();
    await expect(page.getByRole('button',{name:'Pause',exact:true})).toBeVisible();
    await expect(page.locator('.play-clock strong')).toContainText(/\d{2}:\d{2}/);
    await page.getByRole('button',{name:'Pause',exact:true}).click();
    await expect(page.locator('.play .dashboard-widget')).toHaveCount(initialWidgets.length+1);
    await shot('04-play');
    await page.getByRole('button',{name:'Resume',exact:true}).click();
    await expect(page.locator('.play-event.bad').first()).toBeVisible({timeout:60_000});
    await page.getByRole('button',{name:'Pause',exact:true}).click();
    record.midplay={clock:await page.locator('.play-clock strong').textContent(),event:await page.locator('.play-event.bad').first().textContent()};
    expect(record.midplay.event).toMatch(/\d{2}:\d{2}/);
    await shot('05-midplay');
    await page.getByRole('button',{name:'Resume',exact:true}).click();
    await expect(page.getByRole('button',{name:'See results',exact:true})).toBeVisible({timeout:90_000});
    expect((await read()).flow.step).toBe('play');
    await page.getByRole('button',{name:'See results',exact:true}).click();
    await expect(page.getByRole('tab',{name:/\bResults\b/})).toHaveAttribute('aria-selected','true');
    await expect(page.locator('.play-outcomes strong')).toHaveCount(3);
    await expect(page.locator('.results-scenario')).toContainText('Illustrative scenario');
    const result=(await read('/simulation')).result,summary=result.matched.summary;
    const diffs=['lost_units','stockout_sku_days','lost_margin'].map(key=>summary.baseline[key]-summary.scoop[key]);
    await expect(page.locator('.play-outcomes .result-negative')).toHaveCount(diffs.filter(value=>value<0).length);
    await expect(page.locator('.results-view .dashboard-widget')).toHaveCount(initialWidgets.length+1);
    await shot('06-results');
    await page.getByText('See full comparison',{exact:true}).click();
    await expect(page.getByText('Actual approved orders · whole warehouse',{exact:true})).toBeVisible();
    expect(quantities(await read())).toEqual(quantities(initial));
    record.result={matched:result.matched.summary,space_gap:result.matched.relative_pallet_gap,simulation_count:result.matched.simulation_count,differences:diffs,performance_exception:'N5: three-metric superiority remains BLOCKED; walkthrough checks truthful rendering and flow.'};
    expect(record.errors).toEqual([]);
  }finally{
    watchEdits=false;
    for(const id of edits.reverse()){const undo=await request.post(`${endpoint}/edits/${id}/undo`);expect(undo.ok()).toBeTruthy()}
    expect(widgetState(await read('/dashboard'))).toEqual(initialWidgets);
    expect(quantities(await read())).toEqual(quantities(initial));
    record.exact_widget_and_quantity_restoration=true;
    await request.put(endpoint+'/flow',{data:{step:'report'}});
    await writeFile(path.resolve('..','reports','n6-walkthrough.json'),JSON.stringify(record,null,2)+'\n');
  }
});
