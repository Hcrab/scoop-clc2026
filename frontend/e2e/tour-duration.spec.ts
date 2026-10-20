import { test, expect } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { TOUR_COPY as copy } from '../src/tour/copy';

// A paced usability estimate, separate from the fast acceptance checks.
// Reading time is a stated model (200 English words/minute), not a human study.
test.use({viewport:{width:1440,height:900}});
const scenarios = [
  {context:'summer',question:'why',widgets:['stock','space'],speed:2},
  {context:'growing',question:'heat',widgets:['space','cover'],speed:4},
  {context:'unchanged',question:'skip',widgets:['stock'],speed:8},
] as const;

for(const scenario of scenarios) test(`paced tour: ${scenario.context}`,async({page})=>{
  test.setTimeout(480_000);
  const started=Date.now(),entries:any[]=[],errors:string[]=[],writes:string[]=[];
  await page.addInitScript(()=>window.addEventListener('scoop:tour-state',event=>{
    const state=(event as CustomEvent).detail;
    if(state.step==='play'&&state.complete&&!(window as any).__durationCompleteAt)(window as any).__durationCompleteAt=Date.now();
  }));
  page.on('pageerror',e=>errors.push(e.message));
  page.on('request',r=>{if(r.method()!=='GET')writes.push(`${r.method()} ${r.url()}`)});
  const folder=path.resolve('../reports/tour3');await mkdir(folder,{recursive:true});
  const screenshots=path.resolve('../reports/screenshots');await mkdir(screenshots,{recursive:true});
  const coach=page.locator('.tour-coach');
  const next=()=>coach.getByRole('button',{name:copy.next,exact:true}).click();
  async function read(label:string,text:string,inspectSeconds=0){
    const words=text.trim().split(/\s+/).filter(Boolean).length;
    const seconds=Math.max(2,words/200*60)+inspectSeconds;
    entries.push({label,words,reading_seconds:Math.max(2,words/200*60),inspection_seconds:inspectSeconds,at_seconds:(Date.now()-started)/1000});
    console.log(`${scenario.context}: ${label} (${seconds.toFixed(1)}s)`);
    await page.waitForTimeout(seconds*1000);
  }
  async function step(n:number,inspection=0){
    await expect(coach).toHaveAttribute('data-tour-step',String(n));
    await read(`step-${n}`,await coach.locator('h2').innerText()+' '+await coach.locator(':scope>p').allInnerTexts().then(x=>x.join(' ')),inspection);
  }
  try{
    await page.goto('/');await expect(page.getByRole('heading',{name:copy.welcome.title,exact:true})).toBeVisible();
    await expect(page.getByRole('button',{name:copy.welcome.start,exact:true})).toBeEnabled();
    entries.push({label:'entry-loading',wall_seconds:(Date.now()-started)/1000});
    await read('welcome',await page.locator('.tour-modal').innerText());
    await page.getByRole('button',{name:copy.welcome.start,exact:true}).click();
    await step(1,4);await next();await step(2,4);await next();
    await step(3);await page.locator('.cohort-card .cohort-how>summary').first().click();
    await read('expanded-trend-evidence',await page.locator('.cohort-card .cohort-how[open]').first().innerText(),4);await next();
    await step(4,5);await next();await step(5);
    await coach.getByRole('button',{name:copy.questions[scenario.question],exact:true}).click();
    if(scenario.question!=='skip'){
      await expect(coach.getByRole('button',{name:copy.next,exact:true})).toBeVisible();
      await read('assistant-answer',await page.locator('.tour-recorded p').innerText());
    }
    await next();await step(6);await read('context-choices',Object.values(copy.contexts).join(' '));
    await coach.getByRole('button',{name:copy.contexts[scenario.context],exact:true}).click();
    await step(7,3);await expect(coach.getByRole('button',{name:copy.next,exact:true})).toBeVisible();await next();
    await step(8);await page.getByRole('button',{name:'Review orders',exact:true}).click();
    await step(9,5);const ledger=page.locator('.order-ledger').first();
    if(await ledger.count())await read('order-ledger',await ledger.innerText(),3);
    await page.screenshot({path:path.join(screenshots,`tour3-${scenario.context}-09-ledger-with-trend.png`),animations:'disabled'});
    await next();await step(10);await page.getByRole('button',{name:'Approve orders',exact:true}).click();
    await step(11,5);await read('widget-choices',Object.values(copy.widgets).join(' '));
    for(const id of scenario.widgets)await coach.getByRole('button',{name:copy.widgets[id],exact:true}).click();
    if(scenario.widgets.length===2)await page.screenshot({path:path.join(screenshots,`tour3-${scenario.context}-11-two-selected.png`),animations:'disabled'});
    await coach.getByRole('button',{name:copy.addSelected,exact:true}).click();
    await step(12,4);await page.getByRole('button',{name:'Next: Play',exact:true}).click();
    await expect(coach).toHaveAttribute('data-tour-step','13');
    const playStart=Date.now();
    if(scenario.speed!==2)await page.getByRole('button',{name:`${scenario.speed}×`,exact:true}).click();
    // Read while playback proceeds, as the real UI invites the visitor to do.
    await step(13);
    await expect(coach.locator(':scope>p').first()).toHaveText(copy.events.endBody.replaceAll('**',''),{timeout:50_000});
    const completedAt=await page.evaluate(()=>(window as any).__durationCompleteAt as number);
    entries.push({label:'playback',wall_seconds:(Date.now()-playStart)/1000,actual_replay_seconds:(completedAt-playStart)/1000,speed:scenario.speed,overlaps_reading:true});
    await page.getByRole('button',{name:'See results',exact:true}).click();await step(14,6);
    await page.screenshot({path:path.join(screenshots,`tour3-${scenario.context}-14.png`),animations:'disabled'});
    const metrics=await page.locator('.result-metric').allInnerTexts();
    await read('results-comparison',metrics.join(' '));await next();
    await expect(page.getByRole('heading',{name:copy.end.title,exact:true})).toBeVisible();
    await read('end',await page.locator('.tour-modal').innerText());
    expect(errors).toEqual([]);expect(writes).toEqual([]);
    entries.push({label:'complete',wall_seconds:(Date.now()-started)/1000,metrics});
  }finally{
    await writeFile(path.join(folder,`duration-${scenario.context}.json`),JSON.stringify({scenario,reading_model_words_per_minute:200,wall_seconds:(Date.now()-started)/1000,entries,errors,writes},null,2)+'\n');
  }
});
