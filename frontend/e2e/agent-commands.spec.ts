import { test, expect } from '@playwright/test';
import { mkdir,writeFile } from 'node:fs/promises';
import path from 'node:path';
import { offlineASGI } from './support/offline-asgi';

let bridge:ReturnType<typeof offlineASGI>|undefined;
test.afterEach(async({page})=>{await page.unrouteAll({behavior:'ignoreErrors'});bridge?.close();bridge=undefined});

test('specified commands edit real orders through chat and undo exactly',async({page,request:networkRequest})=>{
  test.setTimeout(900_000);page.setDefaultTimeout(60_000);
  if(process.env.SCOOP_TEST_ASGI_OFFLINE==='1'){bridge=offlineASGI();await bridge.attach(page);}
  const request=bridge?.request||networkRequest;
  const provider=process.env.SCOOP_TEST_PROVIDER||'gemini';
  expect((await (await request.get('/health')).json()).provider).toBe(provider);
  const endpoint='/api/plans/P20260727';
  const detail=async()=>{const r=await request.get(endpoint,{timeout:60_000});expect(r.ok()).toBeTruthy();return r.json()};
  const orders=(d:any)=>[...d.orders].sort((a,b)=>a.sku.localeCompare(b.sku));
  const original=await detail();let setupId:number|undefined,editId:number|undefined;
  const records:any[]=[];
  const out=path.resolve('..','reports','screenshots');await mkdir(out,{recursive:true});
  try{
    const setup=await request.put(`${endpoint}/goal`,{data:{goal:original.plan.goal,service_level:original.plan.service_level===.8?.85:.8},timeout:60_000});
    expect(setup.ok()).toBeTruthy();setupId=(await setup.json()).edit_id;
    await page.goto('/');await page.getByRole('tab',{name:/Report & direction|Discover/}).click();
    await expect(page.locator('.cohort-card').first()).toBeVisible({timeout:90_000});
    if(provider==='scripted'){
      const offline=await detail();expect(offline.review.status).toBe('offline');
      expect(offline.review.presentation.html).toContain('data-report-card');
      await expect(page.frameLocator('iframe').locator('[data-report-card]').first()).toBeVisible();
      await page.screenshot({path:path.join(out,'p3-offline-card-list.png')});
    }
    await page.getByRole('button',{name:/Show discussion/}).click();
    const commands=[
      ['the strawberry thing is a summer one-off, it ends 10 Aug','set_override'],
      ['All low-price lines −10%','bulk_edit_orders'],
      ['keep peak below 90%','bulk_edit_orders'],
    ];
    for(const [message,tool] of commands){
      const before=await detail();
      await page.getByRole('textbox',{name:'Discuss this plan'}).fill(message);
      const reply=page.waitForResponse(r=>r.url().endsWith('/chat/stream')&&r.request().method()==='POST',{timeout:180_000});
      await page.getByRole('button',{name:'Send message',exact:true}).click();
      const response=await reply;expect(response.ok()).toBeTruthy();
      const stream=await response.text();
      const event=stream.split('\n\n').find(part=>part.startsWith('event: result\n'));
      expect(event,stream.slice(-2000)).toBeTruthy();
      const result=JSON.parse(event!.slice(event!.indexOf('data: ')+6));
      const action=result.actions.find((a:any)=>a.type==='edit'&&a.edit_id!=null);
      editId=action?.edit_id;
      await writeFile(path.resolve('..','reports',`p3-${provider}-last-response.json`),JSON.stringify(result,null,2));
      expect(result.provider,result.fallback_reason).toBe(provider);
      expect(result.fallback_reason).toBeUndefined();
      expect(action,result.reply).toBeTruthy();editId=action.edit_id;
      if(provider==='gemini')expect(result.tool_trace.some((t:any)=>t.name===tool&&t.status!=='error')).toBeTruthy();
      const after=await detail();expect(orders(after)).not.toEqual(orders(before));
      if(tool==='set_override'){
        const overrides=await (await request.get(`${endpoint}/overrides`)).json();
        expect(overrides.some((o:any)=>o.type==='ends_on'&&o.value==='2026-08-10'&&o.tag_path.some((t:any)=>t.id==='flavour:strawberry'&&t.included))).toBeTruthy();
      }
      if(message.includes('−10%')){
        expect(action.change).toEqual({type:'percent',value:-10});
        expect(action.filter.group||action.filter.tag).toBe('band:price_hkd:0');
        expect(action.filter.district).toBeNull();
        expect(action.filter.cohort).toBeNull();
        for(const row of action.affected_orders)expect(row.after).toBe(Math.round(row.before*.9));
      }
      if(message.includes('90%')){
        expect(action.change).toEqual({type:'fit_capacity',value:.9});
        expect(action.capacity.target_fraction).toBe(.9);
        if(action.capacity.target_met)expect(action.capacity.projected_peak_pallets).toBeLessThanOrEqual(action.capacity.target_pallets+1e-8);
        else expect(action.capacity.inherited_excess_pallets).toBeGreaterThan(0);
      }
      const receipt=page.locator(`.chat-message.assistant .edit-receipt[data-edit-id="${editId}"]`);
      await expect(receipt.getByRole('button',{name:'Undo',exact:true})).toBeVisible();
      await receipt.locator('summary').click();
      await expect(receipt).toContainText('Before');await expect(receipt).toContainText('After');
      await receipt.scrollIntoViewIfNeeded();
      const shot=`p3-${provider}-${records.length+1}.png`;await page.screenshot({path:path.join(out,shot)});
      const undone=page.waitForResponse(r=>r.url().endsWith(`/edits/${editId}/undo`)&&r.request().method()==='POST');
      await receipt.getByRole('button',{name:'Undo',exact:true}).click();expect((await undone).ok()).toBeTruthy();
      expect(orders(await detail())).toEqual(orders(before));editId=undefined;
      records.push({message,tool,provider:result.provider,reply:result.reply,tool_trace:result.tool_trace,affected_orders:action.affected_orders,capacity:action.capacity,exact_undo:true,screenshot:shot});
    }
    await writeFile(path.resolve('..','reports',`p3-${provider}-commands.json`),JSON.stringify(records,null,2));
  }finally{
    if(editId!=null)await request.post(`${endpoint}/edits/${editId}/undo`);
    if(setupId!=null){const restored=await request.post(`${endpoint}/edits/${setupId}/undo`);expect(restored.ok()).toBeTruthy();expect(orders(await detail())).toEqual(orders(original));}
  }
});
