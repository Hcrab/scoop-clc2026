import { test, expect } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { healthAtClock, lowCover } from '../src/dashboardHealth';
import { n, pct } from '../src/api';

test.use({viewport:{width:1440,height:900}});
test('Explore 2×/4×/8× clock, events, tiles and widgets stay synchronized',async({page,request})=>{
  test.setTimeout(150_000);
  const root=path.resolve('..'),integrity=()=>JSON.parse(execFileSync(path.join(root,'.venv/Scripts/python.exe'),[path.join(root,'scripts/tour-integrity.py')],{cwd:root,encoding:'utf8',windowsHide:true}));
  const before=integrity(),pid='P20260727',prefix=`/api/plans/${pid}`;
  const detail=await (await request.get(prefix)).json(),simulation=await (await request.get(prefix+'/simulation')).json(),dashboard=await (await request.get(prefix+'/dashboard')).json(),boot=await (await request.get('/api/bootstrap')).json();
  expect(simulation.status).toBe('ready');expect(detail.flow.max_step).toBe('results');
  const result=simulation.result,records:any[]=[];
  const changed=detail.flow.step!=='play';
  if(changed)expect((await request.put(prefix+'/flow',{data:{step:'play'}})).ok()).toBeTruthy();
  async function snapshot(label:string){
    const day=await page.locator('.play-clock').getAttribute('data-day'),minute=Number(await page.locator('.play-clock').getAttribute('data-minute')),index=result.dates.indexOf(day);
    const health=healthAtClock(dashboard.health,result,boot.products,index,minute);
    const tiles=await page.locator('.dashboard-kpi strong').allTextContents();
    expect(tiles.map(x=>x.trim().replace(/\s+/g,' '))).toEqual([pct(health.fill_rate),`${n(health.stockout_skus.length)} products`,`${n(lowCover(health.products).length)} ${lowCover(health.products).length===1?'product':'products'}`,`${n(health.pallets,1)} / ${n(health.capacity_pallets,1)}`]);
    const expected=result.events.filter((e:any)=>e.date<day!||(e.date===day&&e.minute<=minute)).reverse();
    await expect(page.locator('.play-event')).toHaveCount(expected.length);
    const eventTexts=await page.locator('.play-event>div>p,.play-event>div>details>summary').allTextContents();
    const names=new Map(boot.products.map((p:any)=>[p.sku,p.name]));
    expect(eventTexts).toEqual(expected.map((e:any)=>e.kind==='order'&&e.lines?e.text:e.sku&&!e.text.toLowerCase().includes(String(names.get(e.sku)||'').toLowerCase())?`${names.get(e.sku)||e.sku} · ${e.text}`:e.text));
    const widgets=await page.locator('.dashboard-widget .dashboard-value').allTextContents();
    const scroll=await page.evaluate(()=>({height:document.documentElement.scrollHeight,viewport:innerHeight,top:scrollY}));expect(scroll.height).toBeLessThanOrEqual(scroll.viewport);expect(scroll.top).toBe(0);
    const view={label,day,minute,index,tiles,eventTexts,widgets};records.push(view);return view;
  }
  try{
    await page.addInitScript(()=>localStorage.setItem('scoop:tour-welcome-seen','1'));
    await page.goto('/');await expect(page.getByRole('button',{name:'Replay',exact:true})).toBeVisible();await expect(page.locator('.dashboard-widget')).not.toHaveCount(0);
    await page.getByRole('tab',{name:/Watch/}).click();await expect(page.locator('.watch-step .dashboard-kpi')).toHaveCount(4);
    expect(await page.evaluate(()=>document.documentElement.scrollHeight)).toBe(900);
    await mkdir(path.join(root,'docs/screenshots'),{recursive:true});await page.screenshot({path:path.join(root,'docs/screenshots/tour2-explore-watch.png')});
    await page.getByRole('tab',{name:/Play/}).click();await expect(page.getByRole('button',{name:'Replay',exact:true})).toBeVisible();
    await expect(page.getByRole('button',{name:'2×',exact:true})).toHaveAttribute('aria-pressed','true');
    const epoch=new Date('2026-10-17T00:00:00Z');await page.clock.install({time:epoch});await page.clock.pauseAt(epoch);
    const common:any[]=[];
    for(const speed of [2,4,8]){
      await page.getByRole('button',{name:`${speed}×`,exact:true}).click();
      if(speed!==2){await page.getByRole('button',{name:'Resume',exact:true}).click();await page.clock.fastForward(32_000);await expect(page.getByRole('button',{name:'Replay',exact:true})).toBeVisible()}
      await page.getByRole('button',{name:'Replay',exact:true}).click();await page.clock.runFor(16_000/speed);await page.getByRole('button',{name:'Pause',exact:true}).click();
      const view=await snapshot(`four-days-${speed}x`);expect(view.index).toBe(4);expect(view.minute).toBe(0);common.push(view);
      if(speed===2){await mkdir(path.join(root,'docs/screenshots'),{recursive:true});await page.screenshot({path:path.join(root,'docs/screenshots/tour2-explore-speed.png')})}
    }
    for(const view of common.slice(1)){expect(view.tiles).toEqual(common[0].tiles);expect(view.eventTexts).toEqual(common[0].eventTexts);expect(view.widgets).toEqual(common[0].widgets)}
    await page.getByRole('button',{name:'Resume',exact:true}).click();await page.clock.fastForward(32_000);await page.getByRole('button',{name:'2×',exact:true}).click();await page.getByRole('button',{name:'Replay',exact:true}).click();
    let last=0;
    for(const [speed,days] of [[2,2],[4,4],[8,8]]){
      await page.getByRole('button',{name:`${speed}×`,exact:true}).click();const anchored=await snapshot(`switch-to-${speed}x`);expect(anchored.index*144+anchored.minute/10).toBe(last);
      await page.clock.runFor(4000);const current=await snapshot(`after-${speed}x`);expect(current.index*144+current.minute/10-last).toBe(days*144);last=current.index*144+current.minute/10;
    }
    await page.getByRole('button',{name:'Pause',exact:true}).click();await page.screenshot({path:path.join(root,'docs/screenshots/tour2-explore-mid-switch.png')});
  }finally{
    expect((await request.put(prefix+'/flow',{data:{step:detail.flow.step}})).ok()).toBeTruthy();
    const after=integrity();await mkdir(path.join(root,'reports/tour2'),{recursive:true});await writeFile(path.join(root,'reports/tour2/play-speed.json'),JSON.stringify({records,before,after},null,2)+'\n');expect(after).toEqual(before);
  }
});
