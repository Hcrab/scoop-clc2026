import { test, expect } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

test('N3 report cards, saved evidence URL, observation filters and Results', async ({ page, context, request }) => {
  test.setTimeout(240_000);
  page.setDefaultTimeout(30_000);
  const endpoint='/api/plans/P20260720', out=path.resolve('..','docs','screenshots');
  await mkdir(out,{recursive:true});
  const record:any={mocked_responses:false,screenshots:[],errors:[]};
  page.on('pageerror',error=>record.errors.push(error.message));
  const read=async()=>{const response=await request.get(endpoint);expect(response.ok()).toBeTruthy();return response.json()};
  const shot=async(name:string)=>{const file=`n3-${name}.png`;await page.screenshot({path:path.join(out,file),animations:'disabled'});record.screenshots.push(`docs/screenshots/${file}`)};
  const step=(name:string)=>page.getByRole('tab',{name:new RegExp(`\\b${name}\\b`)});
  try {
    await page.goto('/');
    await step('Report').click();
    await expect(page.locator('.generated-report iframe')).toBeVisible();
    const detail=await read(), cards=detail.cohort_cards;
    expect(cards.length).toBeGreaterThan(0);
    for(const card of cards){
      expect(card.tag_path.some((term:any)=>term.included)).toBeTruthy();
      expect(card.name).not.toMatch(/\bNot\b/);
    }
    const hiddenLeaves=detail.cohort_observations.filter((observation:any)=>!observation.tag_path.some((term:any)=>term.included));
    expect(hiddenLeaves.length).toBeGreaterThan(0);
    expect(hiddenLeaves.every((observation:any)=>!observation.in_card)).toBeTruthy();
    record.cards=cards.map((card:any)=>({id:card.id,name:card.name,case_change:card.case_change}));
    record.observations=detail.cohort_observations.map((o:any)=>({id:o.id,name:o.name,in_card:o.in_card}));
    const frame=page.frameLocator('.generated-report iframe');
    await expect(frame.locator('figure[data-card="cohort"]').first()).toContainText(/cases/);
    await page.evaluate(()=>window.scrollTo(0,0));
    await shot('01-report');
    await frame.locator('figure[data-card="cohort"]').first().scrollIntoViewIfNeeded();
    await shot('02-native-adjustment');

    const queryTrigger=frame.locator('button[data-evidence-id="Q2"]').first();
    await queryTrigger.click();
    await expect(page.getByRole('dialog')).toBeVisible();
    await expect(page).toHaveURL(/\/plans\/P20260720\/evidence\/Q2$/);
    await shot('03-evidence-from-report');
    await page.goBack();
    await expect(page.getByRole('dialog')).toHaveCount(0);

    const setResults=await request.put(endpoint+'/flow',{data:{step:'results'}});
    expect(setResults.ok()).toBeTruthy();
    await page.goto('/plans/P20260720/evidence/Q1');
    const modal=page.getByRole('dialog');
    await expect(modal).toBeVisible();
    await expect(modal).toContainText('Which product groups exist');
    const rows=modal.locator('tbody tr');
    await expect(rows).toHaveCount(25);
    const next=modal.getByRole('button',{name:/Next/});
    await expect(next).toBeEnabled();
    const first=await rows.first().textContent();
    await next.click();
    await expect(rows.first()).not.toHaveText(first||'');
    const sort=modal.locator('thead button').first();
    await sort.click();
    await modal.getByRole('button',{name:'Sort by Sku Count',exact:true}).click();
    const counts=await rows.locator('td:nth-child(4)').allTextContents();
    const numeric=counts.map(text=>Number(text.replaceAll(',','')));
    expect(numeric).toEqual([...numeric].sort((a,b)=>a-b));
    record.numeric_sort=numeric;
    const search=modal.getByRole('searchbox');
    await search.fill('flavour:strawberry');
    await expect(rows.first()).toContainText(/Strawberry/i);
    expect(await rows.count()).toBeLessThanOrEqual(25);
    await shot('04-evidence-search');
    await search.fill('');
    await expect(rows).toHaveCount(25);
    await shot('05-evidence-pages');
    expect((await read()).flow.step).toBe('results');
    const other=await context.newPage();
    await other.goto('/plans/P20260720/evidence/Q1');
    await expect(other.getByRole('dialog')).toContainText('Which product groups exist');
    await other.close();
    await page.bringToFront();
    await page.keyboard.press('Escape');
    await expect(modal).toHaveCount(0);
    await expect(page).not.toHaveURL(/\/evidence\//);

    await step('Report').click();
    const observations=page.locator('details').filter({has:page.locator('summary').filter({hasText:/^All observations/})}).first();
    // A long srcdoc frame needs its compositor position painted after scrolling;
    // otherwise Edge can dispatch the click into the frame's previous hit region.
    await observations.locator(':scope > summary').scrollIntoViewIfNeeded();
    await page.evaluate(()=>new Promise<void>(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve()))));
    if(!await observations.evaluate((node:HTMLDetailsElement)=>node.open))
      await observations.locator(':scope > summary').click();
    await expect(observations).toHaveJSProperty('open',true);
    const inCard=page.getByRole('checkbox',{name:'In a suggestion card',exact:true});
    const outside=page.getByRole('checkbox',{name:'Not in a card',exact:true});
    await expect(inCard).toBeChecked();await expect(outside).toBeChecked();
    await observations.evaluate(node=>node.scrollIntoView({block:'start'}));
    await page.evaluate(()=>window.scrollBy(0,-24));
    await shot('06-observations-both');
    await outside.uncheck();await shot('07-observations-in-cards');
    await outside.check();await inCard.uncheck();await shot('08-observations-outside-cards');
    await inCard.check();
    await step('Watch').click();
    await expect(page.locator('.dashboard-widget').first()).toBeVisible();
    const tops=await page.locator('.dashboard-value').evaluateAll(nodes=>nodes.slice(0,3).map(node=>node.getBoundingClientRect().top));
    record.widget_key_tops=tops;
    expect(Math.max(...tops)-Math.min(...tops)).toBeLessThanOrEqual(1);
    await page.evaluate(()=>window.scrollTo(0,0));await shot('09-round-ticks');
    await step('Results').click();
    await expect(page.locator('.play-outcomes strong')).toHaveCount(3);
    await expect(page.locator('.play-comparison svg')).toBeVisible();
    await expect(page.locator('.dashboard-widget')).toHaveCount(5);
    await page.evaluate(()=>window.scrollTo(0,0));await shot('10-results');
    expect(record.errors).toEqual([]);record.accepted=true;
  } finally {await writeFile(path.resolve('..','reports','n3-polish.json'),JSON.stringify(record,null,2)+'\n')}
});
