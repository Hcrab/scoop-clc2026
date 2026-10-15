import { test, expect } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

test('P8 real Gemini report to evidence, context, orders, widgets and Play result', async ({page,request}) => {
  test.setTimeout(900_000);page.setDefaultTimeout(90_000);
  const endpoint='/api/plans/P20260720',out=path.resolve('..','docs','screenshots');
  await mkdir(out,{recursive:true});
  const record:any={mocked_responses:false,plan:'P20260720',screens:[],widget_edit_ids:[],errors:[]};
  page.on('pageerror',e=>record.errors.push(e.message));
  const read=async(suffix='')=>{const r=await request.get(endpoint+suffix,{timeout:120_000});expect(r.ok(),await r.text()).toBeTruthy();return r.json()};
  const top=()=>page.evaluate(()=>window.scrollTo(0,0));
  const settle=async()=>{await expect(page.locator('.inline-refresh')).toHaveCount(0);await expect(page.getByRole('button',{name:'Settings',exact:true})).toBeEnabled()};
  const take=async(name:string)=>{const file=`p8-${name}.png`;await page.screenshot({path:path.join(out,file)});record.screens.push(`docs/screenshots/${file}`)};
  const orders=(d:any)=>[...d.orders].sort((a,b)=>a.sku.localeCompare(b.sku));
  const quantities=(d:any)=>orders(d).map(o=>({sku:o.sku,cases:o.final_cases??Math.max(0,o.suggested_cases-o.capacity_cut_cases)}));
  const initial=await read(),initialDashboard=await read('/dashboard');
  record.initial={stage:initial.plan.stage,locked_at:initial.plan.locked_at,goal:initial.plan.goal,service_level:initial.plan.service_level,
    orders:orders(initial),widget_ids:initialDashboard.widgets.map((w:any)=>w.id),message_ids:initial.messages.map((m:any)=>m.id)};
  await writeFile(path.resolve('..','reports','p8-walkthrough.json'),JSON.stringify(record,null,2)+'\n');
  expect(initial.plan.stage).toBe('discover');
  expect(initial.review.status).toBe('complete');expect(initial.review.model).toContain('gemini-3.8-flash');
  expect(initial.review.presentation.html).not.toMatch(/<svg\b/i);
  let contextEdit:number|undefined;
  try {
    await page.goto('/');await expect(page.getByRole('tab',{name:/Report & direction/})).toHaveAttribute('aria-selected','true');
    const frame=page.frameLocator('.generated-report iframe');
    await expect(frame.locator('figure[data-chart] svg').first()).toBeVisible();await settle();await top();
    await take('01-report');record.report_model=initial.review.model;
    await frame.locator('article[data-report-card]').nth(1).scrollIntoViewIfNeeded();
    await take('02-report-observation');
    await frame.locator('button[data-evidence-id]').first().click();
    await expect(frame.getByRole('region',{name:/^Evidence /}).first()).toBeVisible();
    await take('03-report-source');
    await top();
    const panel=page.getByRole('complementary',{name:'Demand changes and context'}),card=panel.locator('.cohort-card').first();
    await card.getByRole('button',{name:/^Expand .* trend$/}).click();
    await expect(card.locator('.cohort-chart svg')).toBeVisible();
    await card.getByText('Evidence and products',{exact:true}).click();
    await expect(card.locator('.cohort-table-wrap tbody tr')).toHaveCount(25);
    await card.scrollIntoViewIfNeeded();await take('04-cohort-evidence');
    await card.getByText('Add context',{exact:true}).click();
    await card.locator('.cohort-context select').first().selectOption('ends_on');
    await card.getByLabel('Ends before',{exact:true}).fill('2026-07-27');
    const contextResponse=page.waitForResponse(r=>r.url().endsWith('/overrides')&&r.request().method()==='POST',{timeout:180_000});
    await card.getByRole('button',{name:'Apply context',exact:true}).click();
    const response=await contextResponse;expect(response.ok(),await response.text()).toBeTruthy();
    const edit=await response.json();contextEdit=edit.edit_id;
    expect(edit.affected_orders.some((x:any)=>x.before!==x.after)).toBeTruthy();
    const receipt=panel.locator(`.edit-receipt[data-edit-id="${contextEdit}"]`);
    await receipt.locator('summary').click();await expect(receipt).toContainText('Before');await expect(receipt).toContainText('After');
    await settle();await receipt.scrollIntoViewIfNeeded();await take('05-context-diff');
    record.context={edit_id:contextEdit,ends_on:'2026-07-27',affected_orders:edit.affected_orders};
    const undo=page.waitForResponse(r=>r.url().endsWith(`/edits/${contextEdit}/undo`)&&r.request().method()==='POST');
    await receipt.getByRole('button',{name:'Undo',exact:true}).click();expect((await undo).ok()).toBeTruthy();
    expect(orders(await read())).toEqual(orders(initial));contextEdit=undefined;record.context.exact_undo=true;
    await settle();await top();
    const advance=page.waitForResponse(r=>r.url().endsWith('/advance')&&r.request().method()==='POST');
    await page.getByRole('button',{name:'Review orders',exact:true}).click();expect((await advance).ok()).toBeTruthy();
    await expect(page.getByRole('tab',{name:/Orders/})).toHaveAttribute('aria-selected','true');
    const groups=await read('/order-summary'),first=page.locator('.action-group').first();
    await expect(first.locator('tbody tr')).toHaveCount(20);
    await first.getByRole('button',{name:'Next',exact:true}).click();await expect(first.locator('tbody tr')).toHaveCount(5);
    await first.getByRole('button',{name:'Previous',exact:true}).click();
    expect(await page.locator('.action-capacity').evaluate(el=>getComputedStyle(el).position)).toBe('sticky');
    await first.locator('tbody tr').first().getByText('Order evidence',{exact:true}).click();
    await settle();await top();await take('06-orders');
    record.orders={groups:groups.groups.map((g:any)=>({id:g.id,rows:g.skus.length})),page_rows:20,capacity:groups.capacity};
    const approval=page.waitForResponse(r=>r.url().endsWith('/approve-orders')&&r.request().method()==='POST');
    await page.getByRole('button',{name:'Approve orders',exact:true}).click();expect((await approval).ok()).toBeTruthy();
    await page.getByRole('button',{name:'Dashboard',exact:true}).click();await settle();await top();await take('07-dashboard');
    const stamp=Date.now().toString(36),title=`Warehouse pallets ${stamp}`;
    await page.getByRole('button',{name:'Add widget',exact:true}).click();
    const sheet=page.getByRole('dialog',{name:'Add widget',exact:true});
    await sheet.getByLabel(/^Measure/).selectOption('pallets');await sheet.getByLabel('Title',{exact:true}).fill(title);
    await expect(sheet.locator('.dashboard-preview strong')).toContainText('pallets');await take('08-widget-preview');
    const added=page.waitForResponse(r=>r.url().endsWith('/dashboard')&&r.request().method()==='POST');
    await sheet.getByRole('button',{name:'Add widget',exact:true}).click();const addResponse=await added;
    expect(addResponse.ok()).toBeTruthy();record.widget_edit_ids.push((await addResponse.json()).edit_id);
    await expect(page.locator('.dashboard-widget').filter({has:page.getByRole('heading',{name:title,exact:true})})).toBeVisible();
    await settle();await top();
    const chatTitle=`Warehouse on hand ${stamp}`,message=`Add a warehouse on-hand widget titled "${chatTitle}".`;
    record.chat_message=message;
    await page.getByRole('button',{name:/Show discussion/}).click();await page.getByRole('textbox',{name:'Discuss this plan'}).fill(message);
    const chatResponse=page.waitForResponse(r=>r.url().endsWith('/chat/stream')&&r.request().method()==='POST',{timeout:180_000});
    await page.getByRole('button',{name:'Send message',exact:true}).click();
    const chat=await chatResponse;expect(chat.ok()).toBeTruthy();const stream=await chat.text();
    const event=stream.split('\n\n').find(x=>x.startsWith('event: result\n'));expect(event,stream.slice(-1000)).toBeTruthy();
    const reply=JSON.parse(event!.slice(event!.indexOf('data: ')+6));
    const chatEdit=reply.actions.find((a:any)=>a.type==='edit'&&a.edit_id!=null);
    if(chatEdit)record.widget_edit_ids.push(chatEdit.edit_id);
    expect(reply.provider,reply.fallback_reason).toBe('gemini');expect(reply.fallback_reason).toBeUndefined();
    expect(reply.tool_trace.some((t:any)=>t.name==='add_widget'&&t.status==='ok')).toBeTruthy();
    const chatWidget=page.locator('.dashboard-widget').filter({has:page.getByRole('heading',{name:chatTitle,exact:true})});
    await expect(chatWidget).toBeVisible();await settle();await take('09-gemini-widget');
    const afterChat=await read();record.chat_message_ids=afterChat.messages.filter((m:any)=>
      m.role==='user'&&m.content===message||m.role==='assistant'&&(m.meta?.actions||[]).some((a:any)=>a.edit_id===chatEdit?.edit_id)).map((m:any)=>m.id);
    record.chat={provider:reply.provider,reply:reply.reply,edit_id:chatEdit?.edit_id,
      tool_trace:reply.tool_trace.map((t:any)=>({name:t.name,status:t.status,args:t.args}))};
    await page.getByRole('button',{name:'Hide discussion',exact:true}).click();await top();
    await page.getByRole('button',{name:'Play',exact:true}).click();
    const widgetIds=(await read('/dashboard')).widgets.map((w:any)=>w.id);
    await expect(page.locator('.play .dashboard-widget')).toHaveCount(widgetIds.length);
    await page.getByRole('button',{name:'4×',exact:true}).click();
    const played=page.waitForResponse(r=>r.url().endsWith('/play')&&r.request().method()==='POST',{timeout:240_000});
    await page.getByRole('button',{name:'Play this order through',exact:true}).click();
    const playedResponse=await played;expect(playedResponse.ok(),await playedResponse.text()).toBeTruthy();const sim=await playedResponse.json();
    await expect(page.locator('.play-autopilot')).toHaveText('Week-2 orders are placed automatically on both sides.');
    await expect(page.getByRole('tab',{name:/Orders/})).toBeDisabled();await take('10-play');
    await expect(page.locator('.play-outcomes')).toBeVisible({timeout:90_000});
    const outcomes=page.locator('.play-outcomes strong');await expect(outcomes).toHaveCount(3);
    const n=(value:number,digits=0)=>new Intl.NumberFormat('en-US',{maximumFractionDigits:digits}).format(value);
    await expect(outcomes.nth(0)).toHaveText(n(Math.abs(sim.affected_comparison.units_saved)));
    await expect(outcomes.nth(1)).toHaveText(n(sim.affected_comparison.pallet_difference,1));
    await expect(outcomes.nth(2)).toHaveText(n(Math.abs(sim.affected_comparison.stockout_days_avoided)));
    expect(sim.days).toBe(16);expect(sim.capacity_pallets).toBe(71);
    const stock=page.locator('.play .dashboard-widget').filter({has:page.getByRole('heading',{name:chatTitle,exact:true})});
    await expect(stock.locator('g[data-series="rule"] polyline')).toHaveCount(1);
    const dotDays=sim.runs.baseline.per_sku.lost.filter((row:number[])=>row.some(v=>v>0)).length;
    await expect(stock.locator('g[data-series="dot"] circle')).toHaveCount(dotDays);
    await page.locator('.play-outcomes').scrollIntoViewIfNeeded();await take('11-result');
    await page.getByText('See full comparison',{exact:true}).click();await expect(page.locator('.play-comparison table')).toHaveCount(1);
    await expect(page.locator('.play-comparison caption')).toHaveText('Whole warehouse · 75 affected products');
    await page.locator('.play-comparison').scrollIntoViewIfNeeded();await take('12-comparison');
    await stock.scrollIntoViewIfNeeded();await take('13-two-policy-chart');
    record.play={days:sim.days,start:sim.start,end:sim.end,summary:sim.summary,affected_comparison:sim.affected_comparison,
      affected_skus:sim.affected_skus,widget_ids:widgetIds,rule_stockout_dot_days:dotDays,events:sim.events};
    expect(record.errors).toEqual([]);record.accepted=true;
  } finally {
    try {
    if(contextEdit!=null){const r=await request.post(`${endpoint}/edits/${contextEdit}/undo`);record.context_cleanup_status=r.status()}
    record.widget_undo=[];
    for(const id of [...record.widget_edit_ids].reverse()){
      const r=await request.post(`${endpoint}/edits/${id}/undo`);record.widget_undo.push({id,status:r.status()});
      expect(r.ok(),await r.text()).toBeTruthy();
    }
    expect((await read('/dashboard')).widgets.map((w:any)=>w.id)).toEqual(record.initial.widget_ids);
    // Approval deliberately confirms rows; its fixture cleanup is recorded separately.
    expect(quantities(await read())).toEqual(quantities(initial));
    record.widget_exact_undo=true;record.order_quantities_unchanged=true;
    } finally {
    await writeFile(path.resolve('..','reports','p8-walkthrough.json'),JSON.stringify(record,null,2)+'\n');
    }
  }
});
