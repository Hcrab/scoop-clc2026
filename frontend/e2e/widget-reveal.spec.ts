import { test, expect } from '@playwright/test';
import { mkdir, writeFile, readFile } from 'node:fs/promises';
import path from 'node:path';
import { sentenceTitle } from '../src/OperationalWidget';
import { TOUR_COPY as copy } from '../src/tour/copy';

test.use({viewport:{width:1440,height:900},reducedMotion:'no-preference'});
test('Watch selection reveals, scrolls to and pops the real widget before confirmation',async({page})=>{
  const bundle=JSON.parse(await readFile(path.resolve('public/tour-bundle.json'),'utf8'));
  const stockTitle:string=sentenceTitle(bundle.branches.unchanged.widgets.stock.spec.title);
  const writes:string[]=[],errors:string[]=[];
  page.on('request',r=>{if(r.method()!=='GET')writes.push(r.method()+' '+r.url())});page.on('pageerror',e=>errors.push(e.message));
  await page.goto('/');await page.getByRole('button',{name:copy.welcome.start,exact:true}).click();
  const coach=page.locator('.tour-coach'),next=()=>coach.getByRole('button',{name:'Next',exact:true}).click();
  await next();await next();await page.locator('.cohort-card .cohort-how>summary').first().click();await next();await next();
  await coach.getByRole('button',{name:copy.questions.skip,exact:true}).click();await next();
  await coach.getByRole('button',{name:copy.contexts.unchanged,exact:true}).click();await next();
  await page.getByRole('button',{name:'Review orders',exact:true}).click();await next();
  await page.getByRole('button',{name:'Approve orders',exact:true}).click();await expect(coach).toHaveAttribute('data-tour-step','11');
  await page.evaluate((stockTitle)=>{
    const frames:any[]=[];(window as any).__widgetReveal=frames;
    function sample(){
      const panel=document.querySelector<HTMLElement>('.watch-step>.dashboard');
      const cards=[...document.querySelectorAll<HTMLElement>('.dashboard-widget')].filter(el=>[stockTitle,'Cold-store space'].includes(el.querySelector('h3')?.textContent||''));
      frames.push({at:performance.now(),scroll:panel?.scrollTop,cards:cards.map(el=>({title:el.querySelector('h3')?.textContent,transform:getComputedStyle(el).transform,animations:el.getAnimations().length}))});
      if((window as any).__widgetReveal)requestAnimationFrame(sample);
    }requestAnimationFrame(sample);
  },stockTitle);
  const panel=page.locator('.watch-step>.dashboard'),add=coach.getByRole('button',{name:copy.addSelected,exact:true});
  const widget=(title:string)=>page.locator('.dashboard-widget').filter({has:page.getByRole('heading',{name:title,exact:true})});
  const before=await panel.evaluate(el=>el.scrollTop);
  await coach.getByRole('button',{name:copy.widgets.stock,exact:true}).click();
  await expect(widget(stockTitle)).toHaveCount(1);await expect(coach).toHaveAttribute('data-tour-step','11');
  await expect.poll(()=>panel.evaluate(el=>el.scrollTop)).toBeGreaterThan(before+30);
  await page.waitForTimeout(800);await expect(widget(stockTitle)).toBeInViewport({ratio:.95});
  await coach.getByRole('button',{name:copy.widgets.space,exact:true}).click();
  await expect(widget('Cold-store space')).toHaveCount(1);await page.waitForTimeout(800);await expect(widget('Cold-store space')).toBeInViewport({ratio:.95});
  await coach.getByRole('button',{name:copy.widgets.stock,exact:true}).click();await expect(widget(stockTitle)).toHaveCount(0);await expect(widget('Cold-store space')).toHaveCount(1);
  await coach.getByRole('button',{name:copy.widgets.space,exact:true}).click();await expect(widget('Cold-store space')).toHaveCount(0);await expect(add).toBeDisabled();
  // Rapid choices keep both real cards; the most recent choice receives the camera.
  await coach.getByRole('button',{name:copy.widgets.stock,exact:true}).click();await coach.getByRole('button',{name:copy.widgets.space,exact:true}).click();
  await page.waitForTimeout(800);await expect(widget('Cold-store space')).toBeInViewport({ratio:.95});
  const dir=path.resolve('../reports/screenshots');await mkdir(dir,{recursive:true});await page.screenshot({path:path.join(dir,'watch-widget-reveal.png')});
  const frames=await page.evaluate(()=>{const value=(window as any).__widgetReveal;delete (window as any).__widgetReveal;return value});
  for(const title of [stockTitle,'Cold-store space']){
    const scales=frames.flatMap((f:any)=>f.cards.filter((c:any)=>c.title===title&&c.transform!=='none').map((c:any)=>Number(c.transform.match(/matrix\(([^,]+)/)?.[1])));
    expect(scales.some((v:number)=>v<.99)).toBeTruthy();expect(scales.some((v:number)=>v>1.005)).toBeTruthy();
  }
  await add.click();await expect(coach).toHaveAttribute('data-tour-step','12');
  await expect(widget(stockTitle)).toHaveCount(1);await expect(widget('Cold-store space')).toHaveCount(1);
  expect(await page.evaluate(()=>({height:document.documentElement.scrollHeight,top:scrollY}))).toEqual({height:900,top:0});
  expect(writes).toEqual([]);expect(errors).toEqual([]);
  const report=path.resolve('../reports/widget-reveal');await mkdir(report,{recursive:true});await writeFile(path.join(report,'browser.json'),JSON.stringify({frames,writes,errors,confirmed_once:true},null,2)+'\n');
});
