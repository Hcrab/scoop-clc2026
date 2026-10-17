import { test, expect } from '@playwright/test';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { TOUR_COPY as copy, fillTourCopy as fill } from '../src/tour/copy';

test.use({viewport:{width:1440,height:900}});
const root=path.resolve('..'), output=path.join(root,'docs/screenshots');
const integrity=()=>JSON.parse(execFileSync(path.join(root,'.venv/Scripts/python.exe'),[path.join(root,'scripts/tour-integrity.py')],{cwd:root,encoding:'utf8',windowsHide:true}));
const number=(v:number,digits=0)=>new Intl.NumberFormat('en-US',{maximumFractionDigits:digits,minimumFractionDigits:digits}).format(v);
const plain=(v:string)=>v.replace(/\*\*/g,'');
const date=(v:string)=>new Date(v+'T00:00:00Z').toLocaleDateString('en-GB',{day:'numeric',month:'short',timeZone:'UTC'});

for(const [context,question,widget] of [['summer','why','stock'],['growing','heat','space'],['unchanged','skip','cover']] as const){
test(`real-component tour v2: ${context} / ${question} / ${widget}`,async({page})=>{
  test.setTimeout(150_000);
  const bundle=JSON.parse(await readFile(path.join(root,'frontend/public/tour-bundle.json'),'utf8'));
  const branch=bundle.branches[context],meta=bundle.meta,values=branch.recalculation,before=integrity();
  const record:any={context,question,widget,screenshots:[],geometry:[],copy:[],requests:[],errors:[],moments:[],beats:[]};
  page.on('request',r=>{if(r.method()!=='GET')record.requests.push({method:r.method(),url:r.url()})});
  page.on('pageerror',e=>record.errors.push(e.message));
  await page.addInitScript(()=>{
    const audit={frames:0,overlaps:[] as unknown[]};(window as any).__tourGeometry=audit;
    function sample(){
      const coach=document.querySelector<HTMLElement>('.tour-coach'),cut=document.querySelector('.tour-spotlight rect[fill="black"]');
      if(coach&&cut){const c=coach.getBoundingClientRect(),x=Number(cut.getAttribute('x'))+6,y=Number(cut.getAttribute('y'))+6,w=Number(cut.getAttribute('width'))-12,h=Number(cut.getAttribute('height'))-12;
        const area=Math.max(0,Math.min(c.right,x+w)-Math.max(c.left,x))*Math.max(0,Math.min(c.bottom,y+h)-Math.max(c.top,y));audit.frames++;if(area>1)audit.overlaps.push({step:coach.dataset.tourStep,beat:coach.dataset.tourBeat,area});
      }requestAnimationFrame(sample);
    }requestAnimationFrame(sample);
  });
  await mkdir(output,{recursive:true});await mkdir(path.join(root,'reports/tour2'),{recursive:true});
  const coach=page.locator('.tour-coach');
  const next=()=>coach.getByRole('button',{name:copy.next,exact:true}).click();
  async function rich(locator:any,text:string){
    await expect(locator).toHaveText(plain(text));
    await expect(locator.locator('strong')).toHaveText([...text.matchAll(/\*\*(.*?)\*\*/g)].map(x=>x[1]));
  }
  async function geometry(){
    const cut=page.locator('.tour-spotlight rect[fill="black"]');await expect(cut).toHaveCount(1);
    await page.waitForTimeout(240);
    const c=(await coach.boundingBox())!;
    const t=await cut.evaluate(el=>({x:Number(el.getAttribute('x'))+6,y:Number(el.getAttribute('y'))+6,width:Number(el.getAttribute('width'))-12,height:Number(el.getAttribute('height'))-12}));
    expect(t.width).toBeGreaterThan(0);expect(t.height).toBeGreaterThan(0);
    const overlap=Math.max(0,Math.min(c.x+c.width,t.x+t.width)-Math.max(c.x,t.x))*Math.max(0,Math.min(c.y+c.height,t.y+t.height)-Math.max(c.y,t.y));
    record.geometry.push({step:await coach.getAttribute('data-tour-step'),beat:await coach.getAttribute('data-tour-beat'),coach:c,target:t,overlap});
    expect(overlap,'Coach must not cover its target').toBe(0);
    expect(c.x).toBeGreaterThanOrEqual(0);expect(c.y).toBeGreaterThanOrEqual(0);expect(c.x+c.width).toBeLessThanOrEqual(1441);expect(c.y+c.height).toBeLessThanOrEqual(901);
  }
  async function shot(name:string){const file=`tour2-${context}-${name}.png`;await page.screenshot({path:path.join(output,file),animations:'disabled'});record.screenshots.push('docs/screenshots/'+file)}
  async function check(step:number,body=copy.steps[step as keyof typeof copy.steps].body,suffix=''){
    const entry=copy.steps[step as keyof typeof copy.steps];
    await expect(coach).toHaveAttribute('data-tour-step',String(step));await expect(coach.locator('h2')).toHaveText(entry.title);
    await rich(coach.locator(':scope>p').first(),body);await expect(coach.locator('.tour-coach-top>span')).toHaveText(`Step ${step} of 14`);
    await expect(coach.getByRole('button',{name:copy.skip,exact:true})).toBeVisible();
    const style=await coach.locator('h2').evaluate(el=>({font:getComputedStyle(el).fontSize,weight:getComputedStyle(el).fontWeight,nowrap:getComputedStyle(el).whiteSpace,overflow:el.scrollWidth>el.clientWidth}));
    expect(style).toEqual({font:'20px',weight:'600',nowrap:'nowrap',overflow:false});
    expect(await coach.locator(':scope>p').first().evaluate(el=>[getComputedStyle(el).fontSize,getComputedStyle(el).fontWeight])).toEqual(['15px','400']);
    record.copy.push({step,title:entry.title,body});await geometry();await shot(String(step).padStart(2,'0')+suffix);
  }
  async function noScroll(){const size=await page.evaluate(()=>({height:document.documentElement.scrollHeight,viewport:innerHeight,top:scrollY}));expect(size.height).toBeLessThanOrEqual(size.viewport);expect(size.top).toBe(0)}
  try{
    await page.goto('/');await expect(page.getByRole('heading',{name:copy.welcome.title,exact:true})).toBeVisible();await rich(page.locator('.tour-modal>p'),fill(copy.welcome.body,{capacity:meta.capacity}));await shot('00-welcome');
    await page.getByRole('button',{name:copy.welcome.start,exact:true}).click();await check(1);await next();
    await check(2,fill(copy.steps[2].body,{effect:number(meta.effect)}));
    expect(await page.locator('.generated-report-frame').getAttribute('sandbox')).toBe('allow-scripts');
    const report=page.frameLocator('.generated-report-frame');
    await expect(report.locator('[data-report-card]').filter({has:report.getByRole('heading',{name:/value strawberry water/i})}).first()).toBeInViewport();
    await next();await check(3);const card=page.locator(`.cohort-card[data-cohort-id="${meta.strawberry_card_id}"]`);
    await expect(coach.getByRole('button',{name:copy.next,exact:true})).toHaveCount(0);await card.locator('.cohort-how>summary').click();await expect(coach.getByRole('button',{name:copy.next,exact:true})).toBeVisible();await geometry();await shot('03-drilldown');await next();
    await check(4);await expect(page.getByRole('slider',{name:'In-stock target'})).toBeDisabled();await expect(page.getByRole('slider',{name:'In-stock target'})).toBeInViewport();await expect(card.locator('.cohort-heading h3')).toBeInViewport();await next();
    await check(5);await expect(coach.locator('.tour-choice')).toHaveText(Object.values(copy.questions));await coach.getByRole('button',{name:copy.questions[question],exact:true}).click();
    if(question!=='skip'){await expect(page.locator('.tour-recorded p')).toHaveText(bundle.questions[question].reply);await expect(page.locator('.tour-recorded>span')).toHaveText(copy.recorded);await geometry();await shot('05-answer')}
    await next();await check(6);await expect(coach.locator('.tour-choice')).toHaveText(Object.values(copy.contexts));await coach.getByRole('button',{name:copy.contexts[context],exact:true}).click();
    const body=fill(context==='unchanged'?copy.recalculation.unchanged:context==='growing'&&values.n>0?copy.recalculation.growingWithCut:copy.recalculation[context],{f_before:values.f_before.toFixed(2),f_after:values.f_after.toFixed(2),before:number(values.before),after:number(values.after),p_before:values.p_before.toFixed(1),p_after:values.p_after.toFixed(1),n:number(values.n)});
    await check(7,body,'-beat-1');record.beats.push({beat:1,context:await card.locator('[data-tour-context]').allTextContents()});
    await expect(coach.getByRole('button',{name:copy.next,exact:true})).toHaveCount(0);
    if(context!=='unchanged'){
      await expect(card.locator('[data-tour-context]')).toHaveText(copy.contexts[context]);
      for(const beat of [2,3,4]){await expect(coach).toHaveAttribute('data-tour-beat',String(beat));await geometry();await shot(`07-beat-${beat}`);record.beats.push({beat,factor:await card.locator('[data-tour-factor]').innerText(),cases:await card.locator('[data-tour-cases]').innerText(),peak:await page.locator('[data-tour-peak]').innerText()})}
    }
    await expect(coach.getByRole('button',{name:copy.next,exact:true})).toBeVisible();
    if(context!=='unchanged'){await expect(card.locator('[data-tour-factor]')).toHaveText(values.f_after.toFixed(2)+'×');await expect(card.locator('[data-tour-cases]')).toHaveText(number(values.after)+' cases');await expect(page.locator('[data-tour-peak]')).toHaveText(values.p_after.toFixed(1)+' pallets');await shot('07-complete')}
    await next();await check(8);await page.getByRole('button',{name:'Review orders',exact:true}).click();await check(9);
    await expect(page.locator('.action-capacity')).toContainText(`${number(values.p_after,1)} / ${number(branch.capacity)} pallets`);
    const group=page.locator('.action-group').filter({hasText:'Value price · Strawberry · Water-based'}).first();
    await expect(group).toHaveAttribute('open','');await expect(group.locator('details[open] summary').filter({hasText:'Order evidence'}).first()).toBeVisible();
    const actualCases=await group.locator('input').evaluateAll(nodes=>nodes.reduce((sum,node)=>sum+Number((node as HTMLInputElement).value),0));expect(actualCases).toBe(values.after);
    await next();await check(10);await page.getByRole('button',{name:'Approve orders',exact:true}).click();await check(11);await noScroll();
    await expect(page.locator('.dashboard-kpi')).toHaveCount(4);await expect(coach.locator('.tour-choice')).toHaveText(Object.values(copy.widgets));await coach.getByRole('button',{name:copy.widgets[widget],exact:true}).click();
    await check(12);await expect(page.locator('.dashboard-widget h3').filter({hasText:branch.widgets[widget].spec.title})).toBeInViewport();await noScroll();await page.getByRole('button',{name:'Next: Play',exact:true}).click();
    await check(13);await expect(page.getByRole('button',{name:'2×',exact:true})).toHaveAttribute('aria-pressed','true');await expect(page.getByRole('button',{name:'Pause',exact:true})).toBeHidden();
    const expected=[fill(copy.events.heat,{date:date(branch.moments.heat_date),temp:meta.heat_temp.toFixed(1)})];
    for(const kind of ['strawberry_arrival','stockout'] as const){const e=branch.moments[kind];if(e)expected.push(fill(kind==='stockout'?copy.events.stockout:copy.events.arrival,{date:date(e.date),time:e.time,units:number(e.units),product:e.product}))}
    let last='',speed=2;const deadline=Date.now()+45_000;
    while(Date.now()<deadline){
      const line=await coach.locator('.tour-event').allTextContents();
      if(line[0]&&line[0]!==last){expect(expected).toContain(line[0]);record.moments.push(line[0]);last=line[0];await geometry();await shot('13-event-'+record.moments.length)}
      const day=await page.locator('.play-clock').getAttribute('data-day');
      if(day!>=branch.moments.heat_date&&speed===2){await page.getByRole('button',{name:'4×',exact:true}).click();speed=4}
      if(day!>='2026-08-02'&&speed===4){await page.getByRole('button',{name:'8×',exact:true}).click();speed=8}
      await noScroll();if(await coach.locator(':scope>p').first().innerText()===plain(copy.events.endBody))break;await page.waitForTimeout(50);
    }
    await check(13,copy.events.endBody,'-end');for(const text of expected)expect(record.moments).toContain(text);
    await page.getByRole('button',{name:'See results',exact:true}).click();await check(14);
    const summary=branch.snapshot.simulation.result.summary;
    for(const [title,key] of [['Units short','lost_units'],['Stockout product-days','stockout_sku_days'],['Lost margin','lost_margin']]){const metric=page.locator('.result-metric').filter({has:page.getByRole('heading',{name:title,exact:true})});await expect(metric.locator('.result-rule')).toContainText(number(summary.baseline[key]));await expect(metric.locator('.result-scoop strong')).toHaveText((key==='lost_margin'?'HK$':'')+number(summary.scoop[key]))}
    await page.keyboard.press('ArrowLeft');await expect(coach).toHaveAttribute('data-tour-step','13');await page.getByRole('button',{name:'See results',exact:true}).click();await expect(coach).toHaveAttribute('data-tour-step','14');await next();
    await expect(page.getByRole('heading',{name:copy.end.title,exact:true})).toBeVisible();await rich(page.locator('.tour-modal>p'),copy.end.body);await shot('15-end');
    record.motion=await page.evaluate(()=>(window as any).__tourGeometry);expect(record.motion.frames).toBeGreaterThan(0);expect(record.motion.overlaps).toEqual([]);
    expect(record.requests).toEqual([]);expect(record.errors).toEqual([]);const after=integrity();expect(after.database).toEqual(before.database);expect(after.provider).toEqual(before.provider);record.integrity={before,after,unchanged:true};
    if(context==='unchanged'){await page.getByRole('button',{name:copy.end.replay,exact:true}).click();await expect(coach).toHaveAttribute('data-tour-step','1');expect(integrity()).toEqual(before)}
  }finally{await writeFile(path.join(root,`reports/tour2/tour-${context}.json`),JSON.stringify(record,null,2)+'\n')}
});
}

test('stale source refuses entry; narrow welcome only offers Explore',async({page})=>{
  await page.route('**/api/tour/source',async route=>{const response=await route.fetch();await route.fulfill({json:{...await response.json(),default_order_hash:'changed'}})});
  await page.goto('/');await expect(page.getByRole('button',{name:copy.welcome.start,exact:true})).toBeDisabled();await expect(page.getByRole('alert')).toContainText('stale');
  await page.unroute('**/api/tour/source');await page.setViewportSize({width:1000,height:900});await page.reload();await expect(page.getByRole('button',{name:copy.welcome.start,exact:true})).toHaveCount(0);await expect(page.getByRole('button',{name:copy.welcome.explore,exact:true})).toBeVisible();
});

test('Esc and Skip exit cleanly; top bar, back and keyboard actions work',async({page})=>{
  const before=integrity();await page.goto('/');await page.getByRole('button',{name:copy.welcome.start,exact:true}).click();await expect(page.locator('.tour-coach')).toHaveAttribute('data-tour-step','1');await page.keyboard.press('Escape');
  await expect(page.locator('.tour-coach')).toHaveCount(0);await expect(page.getByRole('tab',{name:/Report/})).toHaveAttribute('aria-selected','true');
  await page.getByRole('button',{name:copy.takeTour,exact:true}).click();await page.getByRole('button',{name:copy.welcome.start,exact:true}).click();await expect(page.locator('.tour-coach')).toHaveAttribute('data-tour-step','1');
  await page.keyboard.press('Space');await expect(page.locator('.tour-coach')).toHaveAttribute('data-tour-step','2');await page.keyboard.press('ArrowLeft');await expect(page.locator('.tour-coach')).toHaveAttribute('data-tour-step','1');await page.keyboard.press('Enter');await expect(page.locator('.tour-coach')).toHaveAttribute('data-tour-step','2');
  await page.getByRole('button',{name:'Catalog',exact:true}).click({force:true});await expect(page.getByRole('heading',{name:'Weekly plan',exact:true})).toBeVisible();
  await page.getByRole('button',{name:copy.skip,exact:true}).click();await expect(page.locator('.tour-coach')).toHaveCount(0);expect(integrity()).toEqual(before);
});

test('Explore preserves existing evidence deep links',async({page})=>{
  await page.addInitScript(()=>localStorage.setItem('scoop:tour-welcome-seen','1'));const bundle=JSON.parse(await readFile(path.join(root,'frontend/public/tour-bundle.json'),'utf8'));const card=bundle.base.detail.cohort_cards.find((c:any)=>c.id===bundle.meta.strawberry_card_id);
  await page.goto(`/plans/${bundle.plan_id}/evidence/Q-cohort-${card.id}`);await expect(page.getByRole('dialog',{name:card.name,exact:true})).toBeVisible();await expect(page.locator('.tour-coach')).toHaveCount(0);
});
