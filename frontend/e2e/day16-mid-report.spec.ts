import {test,expect} from '@playwright/test';
import {writeFile} from 'node:fs/promises';
import path from 'node:path';

test('refreshed Gemini report keeps normal planning-check heading and host-rendered figures',async({page,request})=>{
  const response=await request.get('/api/plans/P20260727');expect(response.ok()).toBeTruthy();
  const detail=await response.json();expect(detail.flow.step).toBe('report');
  expect(detail.review.model).toBe('gemini-3.8-flash');expect(detail.review.presentation.html).not.toMatch(/<svg\b/i);
  await page.goto('/');const frame=page.frameLocator('.generated-report iframe');
  const heading=frame.getByRole('heading',{name:'Merchandising & planning checks',exact:true});
  await expect(heading).toBeVisible();
  const style=await heading.evaluate(el=>({color:getComputedStyle(el).color,transform:getComputedStyle(el).textTransform,text:el.textContent}));
  expect(style.color).toBe(await frame.locator('h2').first().evaluate(el=>getComputedStyle(el).color));
  expect(style.transform).toBe('none');await expect(frame.locator('figure[data-chart] svg').first()).toBeVisible();
  await frame.locator('[data-planning-checks]').screenshot({path:path.resolve('..','docs','screenshots','d4-report-checks.png'),animations:'disabled'});
  await writeFile(path.resolve('..','reports','d4-report-visual.json'),JSON.stringify({model:detail.review.model,style,host_rendered_figures:true},null,2)+'\n');
});
