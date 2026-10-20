import { test, expect } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

test('real cohort context, exact Undo, and service preference change orders', async ({page,request})=>{
  test.setTimeout(360_000);
  page.setDefaultTimeout(20_000);
  const out=path.resolve('..','reports','screenshots');await mkdir(out,{recursive:true});
  const endpoint='/api/plans/P20260727';
  const detail=async()=>{const r=await request.get(endpoint);expect(r.ok()).toBeTruthy();return r.json()};
  const orders=(d:any)=>[...d.orders].sort((a,b)=>a.sku.localeCompare(b.sku));
  let activeEdit:number|undefined;
  let setupEdit:number|undefined;
  const original=await detail();
  try {
    // Recompute the saved pre-correction plan before measuring the context delta.
    // This normal service edit is undone after the test, preserving the original plan.
    const setup=await request.put(`${endpoint}/goal`,{data:{goal:original.plan.goal,service_level:original.plan.service_level===.8?.85:.8},timeout:60_000});
    expect(setup.ok()).toBeTruthy();setupEdit=(await setup.json()).edit_id;
    await page.goto('/');
    await page.getByRole('tab',{name:/Report & direction|Discover/}).click();
    const panel=page.getByRole('complementary',{name:'Demand changes and context'});
    const card=panel.locator('.cohort-card').first();
    await expect(card).toBeVisible({timeout:60_000});
    await expect(card.locator('.cohort-key')).toContainText('cases');
    await expect(card.locator('.cohort-impact')).toContainText('HK$');
    await expect(card.locator('.cohort-impact')).toContainText(/pallets.*Peak capacity:/s);
    await panel.screenshot({path:path.join(out,'p2-cohort-cards.png')});
    const before=await detail();
    await card.getByText('Add context',{exact:true}).click();
    await card.locator('.cohort-context select').first().selectOption('ends_on');
    await card.getByLabel('Ends before',{exact:true}).fill('2026-08-10');
    const changedResponse=page.waitForResponse(r=>r.url().endsWith('/overrides')&&r.request().method()==='POST');
    await card.getByRole('button',{name:'Apply context',exact:true}).click();
    const response=await changedResponse;expect(response.ok()).toBeTruthy();
    const edit=await response.json();activeEdit=edit.edit_id;
    expect(edit.affected_orders.some((r:any)=>r.before!==r.after)).toBeTruthy();
    await expect(panel.locator('.edit-receipt')).toContainText('Plan updated:');
    await panel.locator('.edit-receipt summary').click();
    await expect(panel.locator('.edit-receipt')).toContainText('Before');
    await expect(panel.locator('.edit-receipt')).toContainText('After');
    const changed=await detail();expect(orders(changed)).not.toEqual(orders(before));
    await expect(panel.getByText('Loading changes…',{exact:true})).toHaveCount(0,{timeout:60_000});
    await panel.screenshot({path:path.join(out,'p2-context-diff.png')});
    const contextUndo=page.waitForResponse(r=>r.url().endsWith(`/edits/${activeEdit}/undo`)&&r.request().method()==='POST');
    await panel.getByRole('button',{name:'Undo',exact:true}).click();
    expect((await contextUndo).ok()).toBeTruthy();
    expect(orders(await detail())).toEqual(orders(before));activeEdit=undefined;
    await expect(panel.getByText('Loading changes…',{exact:true})).toHaveCount(0);
    await panel.screenshot({path:path.join(out,'p2-context-undo.png')});
    const slider=panel.getByRole('slider');
    await slider.fill('98'); // Right end: service level 50%, less space.
    const serviceResponse=page.waitForResponse(r=>r.url().endsWith('/goal')&&r.request().method()==='PUT');
    await panel.getByRole('button',{name:'Apply',exact:true}).click();
    const goal=await serviceResponse;expect(goal.ok()).toBeTruthy();
    const goalEdit=await goal.json();activeEdit=goalEdit.edit_id;
    expect(activeEdit).toBeDefined();
    const low=await detail();expect(low.plan.service_level).toBe(.5);
    expect(orders(low)).not.toEqual(orders(before));
    expect(low.orders.every((r:any)=>r.critical_ratio===.5)).toBeTruthy();
    await expect(panel.locator('.cohort-service strong')).toHaveText(/50(?:\.0)?%/);
    await expect(panel.locator('.edit-receipt')).toContainText('Plan updated:');
    await expect(panel.getByText('Loading changes…',{exact:true})).toHaveCount(0,{timeout:60_000});
    await panel.screenshot({path:path.join(out,'p2-service-level.png')});
    const serviceUndo=page.waitForResponse(r=>r.url().endsWith(`/edits/${activeEdit}/undo`)&&r.request().method()==='POST');
    await panel.getByRole('button',{name:'Undo',exact:true}).click();
    expect((await serviceUndo).ok()).toBeTruthy();
    expect(orders(await detail())).toEqual(orders(before));activeEdit=undefined;
    expect((await detail()).plan.service_level).toBe(before.plan.service_level);
    await writeFile(path.resolve('..','reports','p2-browser-acceptance.json'),JSON.stringify({
      plan:'P20260727',mocked_responses:false,orders_compared:before.orders.length,
      context:{type:'ends_on',value:'2026-08-10',affected_orders:edit.affected_orders,exact_undo:true},
      service:{before:before.plan.service_level,after:.5,affected_orders:goalEdit.affected_orders,exact_undo:true},
      screenshots:['p2-cohort-cards.png','p2-context-diff.png','p2-context-undo.png','p2-service-level.png']
    },null,2));
  } finally {
    if(activeEdit!=null)await request.post(`${endpoint}/edits/${activeEdit}/undo`);
    if(setupEdit!=null){const restored=await request.post(`${endpoint}/edits/${setupEdit}/undo`);expect(restored.ok()).toBeTruthy();expect(orders(await detail())).toEqual(orders(original));}
  }
});
