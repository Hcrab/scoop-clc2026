import {test,expect} from '@playwright/test';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import path from 'node:path';

test('M4 midnight widgets accumulate today without connecting an incomplete day to completed totals',async({page,request})=>{
  test.setTimeout(300_000);page.setDefaultTimeout(45_000);
  const endpoint='/api/plans/P20260727',evidence:any={mocked_responses:false,errors:[]};
  page.on('pageerror',error=>evidence.errors.push(error.message));
  const read=async(suffix='')=>{const response=await request.get(endpoint+suffix,{timeout:120_000});expect(response.ok(),await response.text()).toBeTruthy();return response.json()};
  const initial=await read(),dashboard=await read('/dashboard');
  const quantity=(detail:any)=>detail.orders.map((row:any)=>[row.sku,row.effective_cases]).sort((a:any,b:any)=>a[0].localeCompare(b[0]));
  try{
    await request.put(endpoint+'/flow',{data:{step:'report'}});
    await page.goto('/');
    await page.getByRole('button',{name:'Review orders',exact:true}).click();
    await page.getByRole('button',{name:'Approve orders',exact:true}).click();
    await expect.poll(async()=>(await read('/simulation')).status,{timeout:240_000,intervals:[2000]}).toBe('ready');
    const job=await read('/simulation'),result=job.result;
    expect(result.intraday.demand_cdf[5]).toBeGreaterThan(0);
    expect(result.intraday.demand_cdf.at(-1)).toBe(1);
    const start=new Date();
    await page.clock.install({time:start});
    await page.clock.pauseAt(new Date(start.getTime()+1000));
    await page.getByRole('button',{name:'Next: Play',exact:true}).click();
    await page.clock.runFor(1);
    await expect(page.locator('.play-clock')).toHaveAttribute('data-minute','0');
    await page.clock.runFor(4085);
    await page.getByRole('button',{name:'Pause',exact:true}).click();
    const clock=page.locator('.play-clock');
    const at=await clock.getAttribute('data-day'),minute=Number(await clock.getAttribute('data-minute'));
    const day=result.dates.indexOf(at);
    expect(day).toBe(2);expect(minute).toBeGreaterThan(0);expect(minute).toBeLessThan(100);
    evidence.midnight={clock:await clock.locator('strong').textContent(),day,minute,widgets:[]};
    for(let i=0;i<dashboard.widgets.length;i++){
      const widget=dashboard.widgets[i],card=page.locator('.play .dashboard-widget').nth(i);
      const value=await card.locator('.dashboard-value').textContent();
      evidence.midnight.widgets.push({title:widget.title,metric:widget.metric,value});
      if(widget.metric==='requested_vs_expected'||widget.metric==='demand'){
        const indexes=result.skus.flatMap((sku:string,index:number)=>widget.skus.includes(sku)?[index]:[]);
        const today=indexes.reduce((sum:number,index:number)=>sum+result.demand[day][index],0)*result.intraday.demand_cdf[Math.floor(minute/10)];
        expect(today).toBeGreaterThan(0);
        await expect(card.locator('.dashboard-value strong')).toHaveText(`${today.toLocaleString('en-HK',{maximumFractionDigits:0})} units`);
        await expect(card.locator('.dashboard-value')).toContainText('Today so far');
        const series=card.locator('g[data-series="plan"]');
        await expect(series.locator('circle[data-partial="true"]')).toHaveCount(1);
        const points=(await series.locator('polyline').last().getAttribute('points'))!.trim().split(' ');
        const lastX=Number(points.at(-1)!.split(',')[0]);
        const partialX=Number(await series.locator('circle[data-partial="true"]').getAttribute('cx'));
        expect(lastX).toBeLessThan(partialX);
      }
      if(widget.metric==='fill_rate')await expect(card.locator('.dashboard-value strong')).toHaveText('Pending dispatch');
    }
    await mkdir(path.resolve('..','docs','screenshots'),{recursive:true});
    await page.screenshot({path:path.resolve('..','docs','screenshots','m4-midnight.png'),fullPage:true,animations:'disabled'});
    await page.getByRole('button',{name:'Resume',exact:true}).click();
    await page.clock.runFor(result.days*2000+100);
    await expect(page.getByRole('button',{name:'See results',exact:true})).toBeVisible();
    for(let i=0;i<dashboard.widgets.length;i++){
      const widget=dashboard.widgets[i];
      if(widget.metric!=='requested_vs_expected'&&widget.metric!=='demand')continue;
      const indexes=result.skus.flatMap((sku:string,index:number)=>widget.skus.includes(sku)?[index]:[]);
      const full=indexes.reduce((sum:number,index:number)=>sum+result.demand.at(-1)[index],0);
      await expect(page.locator('.play .dashboard-widget').nth(i).locator('.dashboard-value strong')).toHaveText(`${full.toLocaleString('en-HK',{maximumFractionDigits:0})} units`);
    }
    await expect(page.locator('.play circle[data-partial="true"]')).toHaveCount(0);
    const prior=JSON.parse(await readFile(path.resolve('..','reports','m1-replay.json'),'utf8'));
    const flowFields=['date','demand','shipped','lost','lost_margin'];
    const flows=(rows:any[])=>rows.map(row=>Object.fromEntries(flowFields.map(key=>[key,row[key]])));
    evidence.daily_comparison={reference:'reports/m1-replay.json (capacity60 before M2)',current_capacity:result.capacity_pallets,summary:result.summary,
      demand_unchanged:JSON.stringify(result.demand)===JSON.stringify(prior.demand),
      compared_daily_fields:flowFields,
      settled_flows_unchanged:['scoop','baseline'].every(policy=>JSON.stringify(flows(result.runs[policy].daily))===JSON.stringify(flows(prior.runs[policy].daily))),
      inventory_context:{prior_capacity:prior.capacity_pallets,prior_summary:prior.summary,
        differences:['scoop','baseline'].flatMap(policy=>result.runs[policy].daily.flatMap((row:any,i:number)=>{
          const fields=['on_hand','pallets','ordered_cases'].filter(key=>row[key]!==prior.runs[policy].daily[i][key]);
          return fields.length?[{policy,date:row.date,changes:Object.fromEntries(fields.map(key=>[key,{prior:prior.runs[policy].daily[i][key],current:row[key]}]))}]:[];
        })),
        note:'M1 used 60 pallets; M2 increased capacity to 66. Inventory and later orders may differ. The intraday enrich conservation test compares identical-capacity physical arrays before and after enrichment.'}};
    expect(evidence.daily_comparison.demand_unchanged).toBeTruthy();
    expect(evidence.daily_comparison.settled_flows_unchanged).toBeTruthy();
    expect(quantity(await read())).toEqual(quantity(initial));
    expect(evidence.errors).toEqual([]);
    evidence.screenshot='docs/screenshots/m4-midnight.png';evidence.full_day_at_close=true;
  }finally{
    const settings=await(await request.get('/api/demo-settings')).json();
    const reset=await request.post('/api/demo-settings/reset',{data:{scenario_id:settings.scenario_id,week_start:'2026-07-27'}});expect(reset.ok()).toBeTruthy();
    await writeFile(path.resolve('..','reports','m4-browser.json'),JSON.stringify(evidence,null,2)+'\n');
  }
});
