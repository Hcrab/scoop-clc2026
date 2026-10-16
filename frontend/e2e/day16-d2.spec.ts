import {test,expect} from '@playwright/test';
import {mkdir,writeFile} from 'node:fs/promises';
import path from 'node:path';

test('D2 report check heading and Results history use the requested styling',async({page,request})=>{
  test.setTimeout(300_000);page.setDefaultTimeout(45_000);
  const endpoint='/api/plans/P20260727',out=path.resolve('..','docs','screenshots');
  await mkdir(out,{recursive:true});const record:any={mocked_responses:false,errors:[]};
  page.on('pageerror',e=>record.errors.push(e.message));
  const read=async(suffix='')=>{const r=await request.get(endpoint+suffix,{timeout:120_000});expect(r.ok(),await r.text()).toBeTruthy();return r.json()};
  const settings=await(await request.get('/api/demo-settings')).json();
  const reset=async()=>{const r=await request.post('/api/demo-settings/reset',{data:{scenario_id:settings.scenario_id,week_start:'2026-07-27'},timeout:120_000});expect(r.ok()).toBeTruthy()};
  await reset();const original=await read();
  try{
    await page.goto('/');await expect(page.locator('.inline-refresh')).toHaveCount(0);
    const frame=page.frameLocator('.generated-report iframe');
    const heading=frame.getByRole('heading',{name:'Merchandising & planning checks',exact:true});
    await expect(heading).toBeVisible();
    const style=await heading.evaluate(el=>({text:el.textContent,color:getComputedStyle(el).color,transform:getComputedStyle(el).textTransform}));
    const ordinaryHeadingColor=await frame.locator('h2').first().evaluate(el=>getComputedStyle(el).color);
    expect(style.text).toBe('Merchandising & planning checks');expect(style.color).toBe(ordinaryHeadingColor);expect(style.transform).toBe('none');
    const section=frame.locator('[data-planning-checks]');await section.screenshot({path:path.join(out,'d2-report-checks.png'),animations:'disabled'});record.heading=style;
    await page.getByRole('button',{name:'Review orders',exact:true}).click();await page.getByRole('button',{name:'Approve orders',exact:true}).click();
    await expect.poll(async()=>(await read('/simulation')).status,{timeout:240_000,intervals:[2000]}).toBe('ready');
    await expect(page.locator('.dashboard-kpi')).toHaveCount(4);expect(await page.locator('.dashboard').innerText()).not.toContain('Simple rule');
    const now=new Date();await page.clock.install({time:now});await page.clock.pauseAt(new Date(now.getTime()+1000));
    await page.getByRole('button',{name:'Next: Play',exact:true}).click();await expect(page.locator('.play-clock')).toHaveAttribute('data-minute','0');
    await expect(page.getByRole('button',{name:'Pause',exact:true})).toBeVisible();
    const result=(await read('/simulation')).result;await page.clock.runFor(result.days*2000+300);
    await expect(page.getByRole('button',{name:'See results',exact:true})).toBeEnabled();
    await page.getByRole('button',{name:'See results',exact:true}).click();
    await expect(page.locator('.inline-refresh')).toHaveCount(0);await expect(page.locator('.results-chart svg')).toBeVisible();
    await expect(page.locator('.results-view .dashboard-kpi')).toHaveCount(0);
    await expect(page.locator('.play-outcomes strong')).toHaveCount(3);
    const chart=page.locator('.results-chart');await expect(chart.locator('svg')).toHaveCount(1);
    const series:any={};for(const [key,color]of [['history','#9aa6a0'],['plan','#205a4e'],['rule','#b77d36']]){
      const line=chart.locator(`g[data-series="${key}"] polyline`).first();await expect(line).toHaveAttribute('stroke',color);series[key]={stroke:await line.getAttribute('stroke'),points:await line.getAttribute('points')};
    }
    const dashboard=await read('/dashboard');expect(dashboard.health.history.length).toBe(28);
    expect(dashboard.health.history.every((p:any)=>p.date<result.start)).toBeTruthy();
    const finalStock=(policy:string)=>result.runs[policy].per_sku.on_hand.at(-1).reduce((n:number,v:number)=>n+v,0);
    record.stock={recorded_last:dashboard.health.history.at(-1),plan_final:finalStock('scoop'),rule_final:finalStock('baseline'),series};
    const stockWidget=page.locator('.results-view .dashboard-widget').filter({has:page.locator('[data-series="rule"]')}).first();await expect(stockWidget).toBeVisible();
    await page.getByText('See full comparison',{exact:true}).click();await expect(page.locator('.results-table-wrap table')).toBeVisible();
    await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:path.join(out,'d2-results.png'),fullPage:true,animations:'disabled'});
    record.outcomes=await page.locator('.play-outcomes').innerText();record.summary=result.summary;expect(record.errors).toEqual([]);
  }finally{
    await reset();expect((await read()).orders.map((o:any)=>[o.sku,o.final_cases])).toEqual(original.orders.map((o:any)=>[o.sku,o.final_cases]));
    await writeFile(path.resolve('..','reports','d2-browser.json'),JSON.stringify(record,null,2)+'\n');
  }
});
