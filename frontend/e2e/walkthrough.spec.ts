import { test, expect } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { gzipSync } from 'node:zlib';

test('tuned real report → orders → Watch → midnight and noon Play → measured Results', async ({page,request})=>{
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
   const top=async()=>{await page.evaluate(()=>{window.scrollTo(0,0);document.querySelector('.report-column')?.scrollTo(0,0);document.querySelector('.cohort-panel')?.scrollTo(0,0)})};
  const shot=async(name:string)=>{
    await expect(page.locator('.inline-refresh')).toHaveCount(0);
    if(await page.locator('.cohort-panel').count()){
      await expect(page.locator('.cohort-preview-row')).toContainText('cases this week');
      await expect(page.locator('.cohort-preview-row')).not.toContainText(/updating/i);
      await expect(page.getByRole('slider',{name:'In-stock target'})).toBeEnabled();
    }
    await expect.poll(()=>page.locator('.product-icon img').evaluateAll(nodes=>nodes.every(img=>(img as HTMLImageElement).complete&&(img as HTMLImageElement).naturalWidth===256))).toBeTruthy();
    await top();const file=`demo-${name}.png`;await page.screenshot({path:path.join(out,file),fullPage:true,animations:'disabled'});record.screenshots.push(`docs/screenshots/${file}`)
  };
  const quantities=(detail:any)=>detail.orders.map((o:any)=>[o.sku,o.final_cases??Math.max(0,o.suggested_cases-o.capacity_cut_cases)]).sort((a:any,b:any)=>a[0].localeCompare(b[0]));
  const widgetState=(dashboard:any)=>dashboard.widgets.map(({id,title,metric,scope,position,threshold}:any)=>({id,title,metric,scope,position,threshold}));
  const operationalCheck=async(name:string,sinceOrder:boolean)=>{
    const dashboard=page.locator('.dashboard');
    await expect(dashboard.locator('.dashboard-kpi')).toHaveCount(4);
    await expect(dashboard.locator('.dashboard-heading small')).toHaveText(`${sinceOrder?'Since':'Up to'} the order on Mon 27 Jul`);
    for(const tile of await dashboard.locator('.dashboard-kpi').all())await expect(tile).toContainText(sinceOrder?'since 27 Jul':'14 days before 27 Jul');
    const widgets=dashboard.locator('.dashboard-widget');
    for(const widget of await widgets.all()){
      await expect(widget.locator('[data-order-marker="2026-07-27"]')).toHaveCount(1);
      await expect(widget.locator('[data-order-marker] text')).toHaveText('Order placed');
      const keys=await widget.locator('[data-series]').evaluateAll(nodes=>nodes.map(el=>el.getAttribute('data-series')));
      expect(keys.every(key=>key==='history'||key==='plan')).toBeTruthy();
      await expect(widget.locator('[data-band]')).toHaveCount(0);
      await expect(widget.locator('.dashboard-widget-title small')).toHaveCount(0);
      const legend=await widget.locator('.legend span').allTextContents();
      expect(legend.length).toBeLessThanOrEqual(2);
      expect(legend.every(text=>['Before the order','Since the order'].includes(text))).toBeTruthy();
      await widget.locator('.dashboard-evidence summary').click();
    }
    const text=await page.locator(sinceOrder?'.play':'.dashboard').innerText();
    expect(text).not.toMatch(/\b(?:Recorded|Simulated|Requested|rule|Decision)\b/i);
    await writeFile(path.resolve('..','reports','tuning',`demo-${name}-ui.txt`),text+'\n');
    for(const widget of await widgets.all())await widget.locator('.dashboard-evidence summary').click();
    return {text,tiles:await dashboard.locator('.dashboard-kpis').innerText(),widgets:await widgets.locator('h3').allTextContents()};
  };
  const settings=await(await request.get('/api/demo-settings')).json();
  // A UI-only retry may reuse a previously computed real replay after its inputs
  // have been verified externally. The ordinary walkthrough always starts fresh.
  if(process.env.SCOOP_WALKTHROUGH_PREPARED!=='1'){
    const fresh=await request.post('/api/demo-settings/reset',{data:{scenario_id:settings.scenario_id,week_start:'2026-07-27'},timeout:120_000});
    expect(fresh.ok()).toBeTruthy();
  }
  const initial=await read(),dashboard=await read('/dashboard');
  expect(initial.flow).toMatchObject({step:'report',max_step:'report'});
  const initialWidgets=widgetState(dashboard);
  record.initial={stage:initial.plan.stage,quantities:quantities(initial),widgets:initialWidgets};
  expect(initial.review.status).toBe('complete');
  expect(initial.review.model).toBe('gemini-3.8-flash');
  expect(initial.review.presentation.html).not.toMatch(/<svg\b/i);
  expect(quantities(initial).reduce((total:number,row:any)=>total+row[1],0)).toBe(2413);
  expect([...initial.cohort_cards[0].skus].sort()).toEqual(['IC006','IC061','IC062','IC063']);
  expect(initial.cohort_cards[0].capacity_pallets).toBe(62);
  expect(initial.cohort_cards[0].peak_capacity).toBeLessThanOrEqual(62);
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
    await expect(page.getByRole('heading',{name:"This week's direction",exact:true})).toBeVisible();
    await expect(page.getByText('Loading changes…',{exact:true})).toHaveCount(0);
    await shot('01-report');
    record.report={model:initial.review.model,title:initial.review.presentation.title,first_card:initial.cohort_cards[0].name};

    const firstCard=page.locator('.cohort-card').first();
    await firstCard.getByText('How we found it',{exact:true}).click();
    const drill=firstCard.locator('.cohort-drilldown');
    await expect(drill.locator('.drill-row')).toHaveCount(initial.cohort_cards[0].tag_path.length+1);
    const chartBefore=await drill.locator('svg').innerHTML();
    await drill.locator('.drill-row').last().click();
    await expect(drill.locator('.drill-chart-head strong')).toContainText(initial.cohort_cards[0].drilldown.steps.at(-1).label);
    expect(await drill.locator('svg').innerHTML()).not.toBe(chartBefore);
    await drill.getByRole('combobox').selectOption('70');
    await firstCard.scrollIntoViewIfNeeded();
    await page.screenshot({path:path.join(out,'demo-strawberry-drilldown.png'),animations:'disabled'});
    record.screenshots.push('docs/screenshots/demo-strawberry-drilldown.png');
    record.compound_path=initial.cohort_cards[0].drilldown.steps.map(({label,effect_pct,rest_effect_pct}:any)=>({label,effect_pct,rest_effect_pct}));
    await firstCard.getByText('How we found it',{exact:true}).click();

    const ordersStarted=Date.now();
    await page.getByRole('button',{name:'Review orders',exact:true}).click();
    await expect(page.getByRole('tab',{name:/\bOrders\b/})).toHaveAttribute('aria-selected','true');
    await expect(page.locator('.action-group tbody tr').first()).toBeVisible({timeout:120_000});
    record.orders={ready_ms:Date.now()-ordersStarted,capacity_text:await page.locator('.action-capacity strong').textContent()};
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
    record.watch=await operationalCheck('watch',false);
    await shot('03-watch');watchEdits=false;

    record.play_entered_at=new Date().toISOString();
    expect(new Date(prepared.completed_at).getTime()).toBeLessThanOrEqual(new Date(record.play_entered_at).getTime());
    const now=new Date();await page.clock.install({time:now});await page.clock.pauseAt(new Date(now.getTime()+1000));
    await page.getByRole('button',{name:'Next: Play',exact:true}).click();
    await expect(page.getByRole('button',{name:'Pause',exact:true})).toBeVisible();
    const clock=page.locator('.play-clock');await expect(clock).toHaveAttribute('data-minute','0');
    await page.clock.runFor(1);await page.clock.runFor(4085);
    await page.getByRole('button',{name:'Pause',exact:true}).click();
    await expect(clock).toHaveAttribute('data-day','2026-07-29');await expect(clock).toHaveAttribute('data-minute','50');
    await expect(clock.locator('strong')).toHaveText('Wed 29 Jul · 00:50');
    await expect(clock.locator('span')).toHaveText('Day 3 since the order');
    await expect(page.locator('.play .dashboard-widget')).toHaveCount(initialWidgets.length+1);
    await expect(page.locator('.play circle[data-partial="true"]')).toHaveCount(0);
    record.midnight={clock:await clock.innerText(),partial_points:0,...await operationalCheck('midnight',true)};
    await shot('04-midnight');
    await page.getByRole('button',{name:'Resume',exact:true}).click();await page.clock.runFor(990);
    await page.getByRole('button',{name:'Pause',exact:true}).click();
    expect(Number(await clock.getAttribute('data-minute'))).toBeGreaterThanOrEqual(720);
    expect(Number(await clock.getAttribute('data-minute'))).toBeLessThanOrEqual(780);
    expect(await page.locator('.play circle[data-partial="true"]').count()).toBeGreaterThan(0);
    record.noon={clock:await clock.innerText(),partial_points:await page.locator('.play circle[data-partial="true"]').count(),...await operationalCheck('noon',true)};
    await shot('05-noon');
    await page.getByRole('button',{name:'Resume',exact:true}).click();await page.clock.runFor(prepared.result.days*2000+300);
    await expect(page.getByRole('button',{name:'See results',exact:true})).toBeVisible({timeout:90_000});
    expect((await read()).flow.step).toBe('play');
    await page.getByRole('button',{name:'See results',exact:true}).click();
    await expect(page.getByRole('tab',{name:/\bResults\b/})).toHaveAttribute('aria-selected','true');
    await expect(page.locator('.play-outcomes strong')).toHaveCount(3);
    await expect(page.locator('.results-scenario')).toContainText('Illustrative scenario');
    const result=(await read('/simulation')).result,summary=result.summary;
    expect(result).not.toHaveProperty('matched');
    const diffs=['lost_units','stockout_sku_days','lost_margin'].map(key=>summary.baseline[key]-summary.scoop[key]);
    expect(diffs.every(value=>value>0)).toBeTruthy();
    expect([summary.scoop.lost_units,summary.scoop.stockout_sku_days,summary.scoop.lost_margin]).toEqual([4297,36,24271.33]);
    expect([summary.baseline.lost_units,summary.baseline.stockout_sku_days]).toEqual([6063,39]);
    expect(summary.baseline.lost_margin).toBeCloseTo(30849.11,6);
    await expect(page.locator('.play-outcomes .result-negative')).toHaveCount(diffs.filter(value=>value<0).length);
    await expect(page.locator('.results-view .dashboard-widget')).toHaveCount(initialWidgets.length+1);
    for(const widget of await page.locator('.results-view .dashboard-widget').all()){
      const keys=await widget.locator('[data-series]').evaluateAll(nodes=>nodes.map(el=>el.getAttribute('data-series')));
      expect(keys).toEqual(['history','plan','rule']);
      await expect(widget.locator('[data-band]')).toHaveCount(0);
      expect(await widget.locator('.legend span').allTextContents()).toEqual(['Before the order','Scoop plan','Simple rule']);
    }
    const peakText=(value:number)=>value.toLocaleString('en-HK',{maximumFractionDigits:1});
    await expect(page.locator('.results-cold-store')).toHaveText(`Same cold store (${result.capacity_pallets} pallets) · Scoop plan peaks at ${peakText(summary.scoop.peak_pallets)}, Simple rule at ${peakText(summary.baseline.peak_pallets)}`);
    await shot('06-results');
    await page.getByText('See full comparison',{exact:true}).click();
    await expect(page.getByText('Whole warehouse · actual approved orders',{exact:true})).toBeVisible();
    await expect(page.locator('.results-table-wrap table')).toHaveCount(1);
    expect(quantities(await read())).toEqual(quantities(initial));
    record.result={capacity_pallets:result.capacity_pallets,summary,differences:diffs,
      comparison:'Normal policies in the same cold store; no service search or space matching.',
      outcome_note:`Simple rule minus Scoop: ${diffs[0]} units short, ${diffs[1]} stockout product-days, HK$${diffs[2].toFixed(2)} margin lost.`};
    if(process.env.SCOOP_WALKTHROUGH_PREPARED!=='1')await writeFile(path.resolve('..','reports','tuning','demo-replay.json.gz'),gzipSync(JSON.stringify(result)));
    record.reused_computed_replay=process.env.SCOOP_WALKTHROUGH_PREPARED==='1';
    expect(record.errors).toEqual([]);
  }finally{
    watchEdits=false;
    for(const id of edits.reverse()){const undo=await request.post(`${endpoint}/edits/${id}/undo`);expect(undo.ok()).toBeTruthy()}
    expect(widgetState(await read('/dashboard'))).toEqual(initialWidgets);
    expect(quantities(await read())).toEqual(quantities(initial));
    record.exact_widget_and_quantity_restoration=true;
    const restored=await request.post('/api/demo-settings/reset',{data:{scenario_id:settings.scenario_id,week_start:'2026-07-27'},timeout:120_000});
    expect(restored.ok()).toBeTruthy();
    expect((await read()).flow).toMatchObject({step:'report',max_step:'report'});
    record.clean_initial_state_restored_by_reset=true;
    await writeFile(path.resolve('..','reports','tuning','demo-walkthrough.json'),JSON.stringify(record,null,2)+'\n');
  }
});
