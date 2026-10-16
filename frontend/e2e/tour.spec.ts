import { test, expect, type Page } from '@playwright/test';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { TOUR_COPY as copy, fillTourCopy as fill } from '../src/tour/copy';

test.use({viewport:{width:1440,height:900}});
const root=path.resolve('..'), output=path.join(root,'docs/screenshots');
const integrity=()=>JSON.parse(execFileSync(path.join(root,'.venv/Scripts/python.exe'),[path.join(root,'scripts/tour-integrity.py')],{cwd:root,encoding:'utf8',windowsHide:true}));
const number=(value:number,digits=0)=>new Intl.NumberFormat('en-US',{maximumFractionDigits:digits,minimumFractionDigits:digits}).format(value);
const shortDate=(value:string)=>new Date(value+'T00:00:00Z').toLocaleDateString('en-GB',{day:'numeric',month:'short',timeZone:'UTC'});

for(const [context,question,widget] of [['summer','why','stock'],['growing','heat','space'],['unchanged','why','cover']] as const){
test(`real-component tour: ${context} / ${question} / ${widget}`,async({page})=>{
  test.setTimeout(150_000);
  const bundle=JSON.parse(await readFile(path.join(root,'frontend/public/tour-bundle.json'),'utf8'));
  const branch=bundle.branches[context],meta=bundle.meta,before=integrity();
  const record:any={context,question,widget,screenshots:[],geometry:[],copy:[],requests:[],errors:[],moments:[]};
  page.on('request',request=>{if(request.method()!=='GET')record.requests.push({method:request.method(),url:request.url()})});
  page.on('pageerror',error=>record.errors.push(error.message));
  await mkdir(output,{recursive:true});
  await mkdir(path.join(root,'reports/night4'),{recursive:true});
  const coach=page.locator('.tour-coach');
  async function geometry(){
    await expect(page.locator('.tour-spotlight rect[fill="black"]')).toHaveCount(1);
    await page.waitForTimeout(250);
    const c=await coach.boundingBox();
    const t=await page.locator('.tour-spotlight rect[fill="black"]').evaluate(el=>({x:Number(el.getAttribute('x'))+6,y:Number(el.getAttribute('y'))+6,width:Number(el.getAttribute('width'))-12,height:Number(el.getAttribute('height'))-12}));
    expect(c).not.toBeNull();expect(t.width).toBeGreaterThan(0);expect(t.height).toBeGreaterThan(0);
    const overlap=Math.max(0,Math.min(c!.x+c!.width,t.x+t.width)-Math.max(c!.x,t.x))*Math.max(0,Math.min(c!.y+c!.height,t.y+t.height)-Math.max(c!.y,t.y));
    record.geometry.push({step:await coach.getAttribute('data-tour-step'),coach:c,target:t,overlap});
    expect(overlap,'Coach must not cover its target').toBe(0);
    expect(c!.x).toBeGreaterThanOrEqual(0);expect(c!.y).toBeGreaterThanOrEqual(0);
    expect(c!.x+c!.width).toBeLessThanOrEqual(1441);expect(c!.y+c!.height).toBeLessThanOrEqual(901);
  }
  async function shot(step:string){
    const file=`tour-${context}-${step}.png`;
    await page.screenshot({path:path.join(output,file),animations:'disabled'});
    record.screenshots.push('docs/screenshots/'+file);
  }
  async function check(step:number,big:string,small:string,suffix=''){
    await expect(coach).toHaveAttribute('data-tour-step',String(step));
    await expect(coach.locator('h2')).toHaveText(big);
    await expect(coach.locator(':scope>p')).toHaveText(small);
    await expect(coach.locator('.tour-coach-top>span')).toHaveText(`Step ${step} of 10 · ${copy.steps[step as keyof typeof copy.steps].screen}`);
    await expect(coach.getByRole('button',{name:copy.skip,exact:true})).toBeVisible();
    record.copy.push({step,big,small});await geometry();await shot(String(step).padStart(2,'0')+suffix);
  }
  async function next(){await coach.getByRole('button',{name:copy.next,exact:true}).click()}
  try{
    await page.goto('/');
    await expect(page.getByRole('heading',{name:copy.welcome.title,exact:true})).toBeVisible();
    await expect(page.locator('.tour-modal>p')).toHaveText(fill(copy.welcome.body,{capacity:meta.capacity}));
    await shot('00-welcome');
    await page.getByRole('button',{name:copy.welcome.start,exact:true}).click();
    await check(1,copy.steps[1].big,fill(copy.steps[1].small,{effect:number(meta.effect)}));
    const card=page.locator(`.cohort-card[data-cohort-id="${meta.strawberry_card_id}"]`);
    await expect(page.getByRole('slider',{name:'In-stock target'})).toBeDisabled();
    await card.locator('.cohort-how>summary').click();
    await check(2,copy.steps[2].big,fill(copy.steps[2].small,{l1:number(meta.l1),l2:number(meta.l2),l3:number(meta.l3)}));
    await page.keyboard.press('ArrowLeft');await expect(coach).toHaveAttribute('data-tour-step','1');
    await card.locator('.cohort-how>summary').click();await expect(coach).toHaveAttribute('data-tour-step','2');
    await page.keyboard.press('Enter');
    await check(3,copy.steps[3].big,copy.steps[3].small);
    await expect(coach.locator('.tour-choice')).toHaveText(Object.values(copy.questions));
    await coach.getByRole('button',{name:copy.questions[question],exact:true}).click();
    await expect(page.locator('.tour-recorded p')).toHaveText(bundle.questions[question].reply);
    await expect(page.locator('.tour-recorded>span')).toHaveText(copy.recorded);
    await geometry();await shot('03-answer');await next();
    await check(4,copy.steps[4].big,copy.steps[4].small);
    await expect(coach.locator('.tour-choice')).toHaveText(Object.values(copy.contexts));
    await coach.getByRole('button',{name:copy.contexts[context],exact:true}).click();
    const contextLine=fill(context==='unchanged'?copy.contextUnchanged:copy.contextResult,{before:number(branch.before_cases),after:number(branch.after_cases)});
    await expect(coach.locator(':scope>p')).toHaveText(contextLine);
    await expect(page.locator('.tour-recorded p')).toHaveText(branch.answer.reply);
    await expect(page.locator('.app')).not.toContainText('Optimistic user-context preset',{useInnerText:true});
    if(context!=='unchanged')await expect(card.locator('.tour-context-result .edit-receipt')).toBeVisible();
    await geometry();await shot('04-result');await next();
    await check(5,copy.steps[5].big,copy.steps[5].small);
    await page.getByRole('button',{name:'Review orders',exact:true}).click();
    await check(6,copy.steps[6].big,fill(copy.steps[6].small,{cases:number(branch.total_cases),peak:number(branch.peak,1),capacity:number(branch.capacity)}));
    await expect(page.locator('.action-capacity')).toContainText(`${number(branch.peak,1)} / ${number(branch.capacity)} pallets`);
    await page.getByRole('button',{name:'Approve orders',exact:true}).click();
    await check(7,copy.steps[7].big,copy.steps[7].small);
    await expect(page.locator('.dashboard-kpi')).toHaveCount(4);
    for(const tile of await page.locator('.dashboard-kpi').all())await expect(tile).toBeInViewport();
    await expect(coach.locator('.tour-choice')).toHaveText(Object.values(copy.widgets));
    await coach.getByRole('button',{name:copy.widgets[widget],exact:true}).click();
    await expect(coach.locator('h2')).toHaveText(copy.steps[7].afterBig);
    await expect(page.locator('.dashboard-widget h3').filter({hasText:branch.widgets[widget].spec.title})).toBeVisible();
    await geometry();await shot('07-widget');
    await page.getByRole('button',{name:'Next: Play',exact:true}).click();
    await check(8,copy.steps[8].big,copy.steps[8].small,'-start');
    await expect(page.getByRole('button',{name:'Pause',exact:true})).toBeHidden();
    let last='',lastDay='';const deadline=Date.now()+50_000;
    const expectedMoments=[copy.steps[8].small,fill(copy.steps[8].heat,{date:shortDate(branch.moments.heat_date)}),fill(copy.steps[8].end,{end_date:shortDate(branch.snapshot.simulation.result.end)})];
    for(const kind of ['strawberry_arrival','stockout'] as const){const e=branch.moments[kind];if(e)expectedMoments.push(fill(kind==='stockout'?copy.steps[8].stockout:copy.steps[8].arrival,{date:shortDate(e.date),time:e.time,units:number(e.units),product:e.product}))}
    while(Date.now()<deadline){
      const text=await coach.locator(':scope>p').innerText();
      expect(expectedMoments).toContain(text);
      if(text!==last){record.moments.push(text);last=text;await geometry();await shot('08-moment-'+record.moments.length)}
      const day=await page.locator('.play-clock').getAttribute('data-day');
      if(day!==lastDay){lastDay=day;const size=await page.evaluate(()=>({height:document.documentElement.scrollHeight,viewport:innerHeight,top:scrollY}));expect(size.height).toBeLessThanOrEqual(size.viewport);expect(size.top).toBe(0)}
      if(await coach.locator('h2').innerText()===copy.steps[8].afterBig)break;
      await page.waitForTimeout(50);
    }
    await check(8,copy.steps[8].afterBig,expectedMoments[2],'-end');
    const observed=[...record.moments,...record.copy.filter((row:any)=>row.step===8).map((row:any)=>row.small)];
    for(const expected of expectedMoments)expect(observed).toContain(expected);
    await page.getByRole('button',{name:'See results',exact:true}).click();
    await check(9,copy.steps[9].big,copy.steps[9].small);
    const summary=branch.snapshot.simulation.result.summary;
    const metrics=[['Units short','lost_units'],['Stockout product-days','stockout_sku_days'],['Lost margin','lost_margin']];
    for(const [title,key] of metrics){const card=page.locator('.result-metric').filter({has:page.getByRole('heading',{name:title,exact:true})});await expect(card.locator('.result-rule')).toContainText(number(summary.baseline[key]));await expect(card.locator('.result-scoop strong')).toHaveText((key==='lost_margin'?'HK$':'')+number(summary.scoop[key]))}
    await page.keyboard.press('ArrowLeft');
    await expect(coach).toHaveAttribute('data-tour-step','8');
    await expect(coach.locator('h2')).toHaveText(copy.steps[8].afterBig);
    await page.getByRole('button',{name:'See results',exact:true}).click();
    await expect(coach).toHaveAttribute('data-tour-step','9');
    await next();
    await expect(page.getByRole('heading',{name:copy.end.title,exact:true})).toBeVisible();
    await expect(page.locator('.tour-modal>p')).toHaveText(copy.end.body);await shot('10-end');
    expect(record.requests).toEqual([]);expect(record.errors).toEqual([]);
    const after=integrity();expect(after.database).toEqual(before.database);expect(after.provider).toEqual(before.provider);
    record.integrity={before,after,unchanged:true};
    if(context==='unchanged'){
      await page.getByRole('button',{name:copy.end.replay,exact:true}).click();
      await expect(coach).toHaveAttribute('data-tour-step','1');
      await expect(coach.locator(':scope>p')).toHaveText(fill(copy.steps[1].small,{effect:number(meta.effect)}));
      expect(integrity()).toEqual(before);
    }
  }finally{await writeFile(path.join(root,`reports/night4/tour-${context}.json`),JSON.stringify(record,null,2)+'\n')}
});
}

test('stale source refuses entry; narrow welcome only offers Explore',async({page})=>{
  await page.route('**/api/tour/source',async route=>{const response=await route.fetch();await route.fulfill({json:{...await response.json(),default_order_hash:'changed'}})});
  await page.goto('/');await expect(page.getByRole('button',{name:copy.welcome.start,exact:true})).toBeDisabled();
  await expect(page.getByRole('alert')).toContainText('stale');
  await page.unroute('**/api/tour/source');await page.setViewportSize({width:1000,height:900});await page.reload();
  await expect(page.getByRole('button',{name:copy.welcome.start,exact:true})).toHaveCount(0);
  await expect(page.getByRole('button',{name:copy.welcome.explore,exact:true})).toBeVisible();
});

test('Esc exits to default Report; top bar starts another clean local tour',async({page})=>{
  const before=integrity();await page.goto('/');await page.getByRole('button',{name:copy.welcome.start,exact:true}).click();
  await expect(page.locator('.tour-coach')).toHaveAttribute('data-tour-step','1');await page.keyboard.press('Escape');
  await expect(page.locator('.tour-coach')).toHaveCount(0);await expect(page.getByRole('tab',{name:/Report/})).toHaveAttribute('aria-selected','true');
  await page.getByRole('button',{name:copy.takeTour,exact:true}).click();await page.getByRole('button',{name:copy.welcome.start,exact:true}).click();
  await expect(page.locator('.tour-coach')).toHaveAttribute('data-tour-step','1');
  await page.locator('.cohort-how>summary').first().click();
  await expect(page.locator('.tour-coach')).toHaveAttribute('data-tour-step','2');
  await page.keyboard.press('Space');await expect(page.locator('.tour-coach')).toHaveAttribute('data-tour-step','3');
  await page.keyboard.press('ArrowLeft');await expect(page.locator('.tour-coach')).toHaveAttribute('data-tour-step','2');
  await page.keyboard.press('Enter');await expect(page.locator('.tour-coach')).toHaveAttribute('data-tour-step','3');
  await page.getByRole('button',{name:copy.questions.why,exact:true}).click();
  await page.locator('.tour-coach').getByRole('button',{name:copy.next,exact:true}).click();
  await expect(page.locator('.tour-coach')).toHaveAttribute('data-tour-step','4');
  await page.keyboard.press('ArrowLeft');await expect(page.locator('.tour-coach')).toHaveAttribute('data-tour-step','3');
  await page.getByRole('button',{name:'Catalog',exact:true}).click({force:true});
  await expect(page.getByRole('heading',{name:'Weekly plan',exact:true})).toBeVisible();
  await page.getByRole('button',{name:copy.skip,exact:true}).click();
  await expect(page.locator('.tour-coach')).toHaveCount(0);expect(integrity()).toEqual(before);
});

test('Explore preserves existing evidence deep links',async({page})=>{
  await page.addInitScript(()=>localStorage.setItem('scoop:tour-welcome-seen','1'));
  const bundle=JSON.parse(await readFile(path.join(root,'frontend/public/tour-bundle.json'),'utf8'));
  const card=bundle.base.detail.cohort_cards.find((c:any)=>c.id===bundle.meta.strawberry_card_id);
  await page.goto(`/plans/${bundle.plan_id}/evidence/Q-cohort-${card.id}`);
  await expect(page.getByRole('dialog',{name:card.name,exact:true})).toBeVisible();
  await expect(page.locator('.tour-coach')).toHaveCount(0);
});
