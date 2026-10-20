import { test, expect } from '@playwright/test';
import { createServer } from 'vite';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';

test('every catalog SKU renders an image and tag SVG at 32, 48 and 96 pixels', async ({ page, request }) => {
  const response=await request.get('/api/bootstrap');
  expect(response.ok()).toBeTruthy();
  const {products}=await response.json();
  expect(products).toHaveLength(75);
  const server=await createServer({server:{middlewareMode:true},appType:'custom'});
  try {
    const {ProductIcon}=await server.ssrLoadModule('/src/ProductIcon.tsx');
    const {productVisuals}=await server.ssrLoadModule('/src/productVisuals.ts');
    expect(Object.keys(productVisuals).sort()).toEqual(products.map((p:any)=>p.sku).sort());
    const fragments=products.flatMap((product:any)=>[32,48,96].map(size=>
      `<div data-sku="${product.sku}" data-size="${size}">${renderToStaticMarkup(createElement(ProductIcon,{sku:product.sku,size}))}</div>`));
    const unknown=renderToStaticMarkup(createElement(ProductIcon,{sku:'NEW-SKU',size:48,product:{name:'New mango cone',format:'cone',tags:[{id:'flavour:mango',dimension:'flavour',name:'Mango',value:1}]}}));
    expect(unknown).toContain('<svg');expect(unknown).not.toContain('<img');
    const css=await readFile(path.resolve('src/productIcon.css'),'utf8');
    await page.goto('/');
    await page.setContent(`<style>${css}</style><main>${fragments.join('')}</main>`);
    const icons=page.locator('main .product-icon');
    await expect(icons).toHaveCount(225);
    await expect(page.locator('main .product-icon-fallback')).toHaveCount(225);
    const sizes=await icons.evaluateAll(nodes=>nodes.map(node=>({width:node.getBoundingClientRect().width,height:node.getBoundingClientRect().height,want:Number(node.parentElement!.dataset.size)})));
    expect(sizes.every(s=>s.width===s.want&&s.height===s.want)).toBeTruthy();
    const shapes=await page.locator('main [data-size="48"] svg').evaluateAll(nodes=>nodes.map(node=>node.innerHTML));
    expect(new Set(shapes).size).toBeGreaterThan(35);
    await writeFile(path.resolve('..','reports','n4-icon-coverage.json'),JSON.stringify({skus:products.length,sizes:[32,48,96],rendered:225,tag_svg_variants:new Set(shapes).size,unknown_sku_fallback:true},null,2)+'\n');
  } finally {await server.close()}
});

test('illustrations load across report, Orders, Play widgets and timed events', async ({ page, request }) => {
  test.setTimeout(180_000);
  const endpoint='/api/plans/P20260720', out=path.resolve('..','reports','screenshots');
  await mkdir(out,{recursive:true});
  const record:any={mocked_responses:false,screenshots:[],errors:[]};
  page.on('pageerror',error=>record.errors.push(error.message));
  const shot=async(name:string)=>{const file=`n4-${name}.png`;await page.screenshot({path:path.join(out,file),animations:'disabled'});record.screenshots.push(`reports/screenshots/${file}`)};
  const step=(name:string)=>page.getByRole('tab',{name:new RegExp(`\\b${name}\\b`)});
  const loaded=async(selector:string)=>{
    const images=page.locator(selector);
    await expect(images.first()).toBeVisible();
    await expect.poll(()=>images.evaluateAll(nodes=>nodes.every(img=>(img as HTMLImageElement).complete&&(img as HTMLImageElement).naturalWidth===256))).toBeTruthy();
  };
  const before=await (await request.get(endpoint)).json();
  const widgetsBefore=await (await request.get(endpoint+'/dashboard')).json();
  try {
    await page.goto('/');await step('Report').click();
    await loaded('.cohort-card .product-icon img');
    const frame=page.frameLocator('.generated-report iframe');
    const native=frame.locator('figure[data-card="cohort"]').first();
    await expect(native.locator('.product-icon img')).toBeVisible();
    await expect.poll(()=>native.locator('.product-icon img').evaluate((img:HTMLImageElement)=>img.complete&&img.naturalWidth===256)).toBeTruthy();
    await page.evaluate(()=>window.scrollTo(0,0));await shot('01-report-cohort');
    await native.scrollIntoViewIfNeeded();await shot('02-native-card');
    record.cohort_representatives=before.cohort_cards.map((c:any)=>({id:c.id,sku:c.representative_sku}));
    const cohortWidgets=widgetsBefore.widgets.filter((w:any)=>w.scope.kind==='cohort');
    for(const w of cohortWidgets)expect(w.representative_sku).toBe(before.cohort_cards.find((c:any)=>c.id===w.scope.key)?.representative_sku);
    await step('Orders').click();await loaded('.action-product .product-icon img');
    await page.evaluate(()=>window.scrollTo(0,0));await shot('03-orders');
    await page.getByRole('button',{name:'Approve orders',exact:true}).click();
    await expect(page.locator('.dashboard-widget')).toHaveCount(widgetsBefore.widgets.length);
    await loaded('.dashboard-widget .product-icon img');
    await expect(page.locator('.dashboard-widget .product-icon')).toHaveCount(cohortWidgets.length);
    const keyTops=await page.locator('.dashboard-value').evaluateAll(nodes=>nodes.slice(0,3).map(node=>node.getBoundingClientRect().top));
    expect(Math.max(...keyTops)-Math.min(...keyTops)).toBeLessThanOrEqual(1);record.widget_key_tops=keyTops;
    await page.getByRole('button',{name:'Next: Play',exact:true}).click();
    await expect(page.locator('.play-clock')).toHaveAttribute('data-day',/2026-/);
    await expect(page.locator('.play-event .product-icon img').first()).toBeVisible({timeout:45_000});
    await page.getByRole('button',{name:'Pause',exact:true}).click();
    await loaded('.dashboard-widget .product-icon img');await loaded('.play-event .product-icon img');
    await page.evaluate(()=>window.scrollTo(0,0));await shot('04-play-widget-event');
    const event=page.locator('.play-event').filter({has:page.locator('.product-icon img')}).first();
    record.timed_event=await event.innerText();expect(record.timed_event).toMatch(/\d{2}:\d{2}/);
    record.play_minute=await page.locator('.play-clock').getAttribute('data-minute');
    await event.scrollIntoViewIfNeeded();await shot('05-event');
    const {products}=await (await request.get('/api/bootstrap')).json();
    record.assets=[];
    for(const p of products){const asset=await request.get(`/products/${p.sku}.webp`);expect(asset.ok(),p.sku).toBeTruthy();const bytes=(await asset.body()).byteLength;expect(bytes,p.sku).toBeLessThan(30_000);record.assets.push({sku:p.sku,bytes})}
    const after=await (await request.get(endpoint)).json();
    expect(after.orders).toEqual(before.orders);
    const widgetsAfter=await (await request.get(endpoint+'/dashboard')).json();
    expect(widgetsAfter.widgets).toEqual(widgetsBefore.widgets);
    expect(record.errors).toEqual([]);record.accepted=true;
  } finally {await writeFile(path.resolve('..','reports','n4-browser.json'),JSON.stringify(record,null,2)+'\n')}
});

test('missing product images expose the actual SVG fallback in app and report', async ({ page }) => {
  const requests:string[]=[];
  page.on('requestfailed',request=>requests.push(request.url()));
  await page.route('**/products/*.webp',route=>route.abort('failed'));
  await page.goto('/');
  await page.getByRole('tab',{name:/\bReport\b/}).click();
  const card=page.locator('.cohort-card').first();
  await expect(card.locator('.product-icon-fallback')).toBeVisible();
  await expect(card.locator('.product-icon img')).toHaveCount(0);
  const native=page.frameLocator('.generated-report iframe').locator('figure[data-card="cohort"]').first();
  await expect(native.locator('.product-icon-fallback')).toBeVisible();
  await expect.poll(()=>native.locator('.product-icon img').evaluate((img:HTMLImageElement)=>img.complete)).toBeTruthy();
  await writeFile(path.resolve('..','reports','n4-fallback.json'),JSON.stringify({failed_requests:requests,image:await native.locator('.product-icon img').evaluate((img:HTMLImageElement)=>({complete:img.complete,width:img.naturalWidth,hidden:img.hidden,display:img.style.display}))},null,2)+'\n');
  await expect(native.locator('.product-icon img')).toBeHidden();
  await page.getByRole('tab',{name:/\bOrders\b/}).click();
  const order=page.locator('.action-product').first();
  await expect(order.locator('.product-icon-fallback')).toBeVisible();
  await expect(order.locator('.product-icon img')).toHaveCount(0);
});
