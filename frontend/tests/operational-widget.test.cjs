const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const Module=require('node:module');
const {test}=require('node:test');
const ts=require('typescript');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const loaded=new Map();
function load(name){
  const base=path.join(__dirname,'..','src',name);
  const file=fs.existsSync(base)?base:['.ts','.tsx'].map(ext=>base+ext).find(file=>fs.existsSync(file));
  if(file.endsWith('.css'))return {};
  if(loaded.has(file))return loaded.get(file).exports;
  const mod=new Module(file,module);mod.filename=file;mod.paths=Module._nodeModulePaths(path.dirname(file));loaded.set(file,mod);
  const normal=mod.require.bind(mod);
  mod.require=id=>id.startsWith('./')?load(id.slice(2)):normal(id);
  mod._compile(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,file);
  return mod.exports;
}
const {OperationalWidget,operationalData,operationalPoint,sentenceTitle,orderDateLabel}=load('OperationalWidget');
const {Dashboard}=load('Dashboard');
const order='2026-07-27';
const products=[{sku:'a',units_per_case:1,cases_per_pallet:10},{sku:'b',units_per_case:1,cases_per_pallet:10}];
const run={daily:[{pallets:1},{pallets:.5},{pallets:.2}],per_sku:{on_hand:[[8,2],[4,1],[1,1]],shipped:[[2,2],[4,1],[3,0]],lost:[[0,0],[0,1],[0,0]],arrived:[[0,0],[0,0],[0,0]]},hourly:{}};
const result={dates:[order,'2026-07-28','2026-07-29'],skus:['a','b'],demand:[[2,2],[4,2],[3,0]],runs:{scoop:run},intraday:{minutes:Array.from({length:145},(_,i)=>i*10),opening_on_hand:[10,4],dispatch_cdf:Array(145).fill(0),demand_cdf:Array(145).fill(.5),arrival_minutes:[[120,120],[120,120],[120,120]]}};
Object.defineProperty(result.runs,'baseline',{get(){throw Error('baseline accessed outside Results')}});
const health={products:products.map((p,i)=>({...p,daily_demand:2,days_cover:i?2:5,recent_demand:Array(7).fill(2)}))};
const widget=metric=>({id:metric,title:'Stock On Hand',scope:{kind:'warehouse'},metric,skus:['a','b'],unit:metric==='lowest_cover'||metric==='days_cover'?'days':metric==='fill_rate'?'ratio':metric==='pallets'?'pallets':'units',series:[{date:'2026-07-24',value:20},{date:'2026-07-25',value:null},{date:'2026-07-26',value:14}],value:14,recent_demand:Array(7).fill(null).map((_,i)=>({date:`2026-07-${20+i}`,value:4}))});
const render=(metric,day=2,minute=720,replay=result)=>renderToStaticMarkup(React.createElement(OperationalWidget,{widget:widget(metric),result:replay,products,health,recordedHealth:health,day,minute,orderDate:order}));

test('all operational metrics render only one measure and two color labels, never reference or risk series',()=>{
  for(const metric of ['on_hand','days_cover','pallets','fill_rate','lost_units','demand','requested_vs_expected','lowest_cover']){
    const html=render(metric);
    assert.match(html,/Order placed/);assert.match(html,/data-order-marker="2026-07-27"/);
    assert.doesNotMatch(html,/Recorded|Simulated|Requested|Simple rule|Safe zone|Safety requirement|Stockout|data-band|cover-list/);
    const svg=html.match(/<svg[^]*?<\/svg>/)[0];
    assert.deepEqual([...svg.matchAll(/data-series="([^"]+)"/g)].map(m=>m[1]),['history','plan']);
    assert.doesNotMatch(svg,/#c96c59|#c18b2c|#4e83b8|#b77d36/);
    assert.equal((svg.match(/data-partial="true"/g)||[]).length,1);
    assert.match(html,/Before the order/);assert.match(html,/Since the order/);
    if(metric==='requested_vs_expected')assert.match(html,/Store requests/);
  }
});

test('Watch retains order-date marker without manufacturing a future metric value',()=>{
  const rows=operationalData(widget('on_hand'),undefined,products,health,-1,null,order);
  assert.equal(rows.at(-1).date,order);assert.ok(Number.isNaN(rows.at(-1).plan));assert.ok(Number.isNaN(rows.at(-1).history));
  assert.ok(Number.isNaN(rows[1].history));
  const html=render('on_hand',-1,null,undefined);
  assert.match(html,/Order placed/);assert.doesNotMatch(html,/data-partial/);
});

test('current daily point begins at noon, remains disconnected, and settles at closing time',()=>{
  for(const metric of ['on_hand','fill_rate','demand','lowest_cover']){
    const morning=render(metric,2,710),noon=render(metric,2,720),closed=render(metric,2,1430);
    assert.doesNotMatch(morning,/data-partial="true"/);
    assert.equal((noon.match(/data-partial="true"/g)||[]).length,1);
    const plan=noon.match(/data-series="plan"[^]*?<\/g>/)[0];
    const line=plan.match(/<polyline[^>]*points="([^"]+)"/);
    assert.equal(line[1].trim().split(/\s+/).length,2);
    assert.match(plan,/fill="var\(--paper, #fff\)"/);
    assert.doesNotMatch(closed,/data-partial="true"/);
    const rows=operationalData(widget(metric),result,products,health,2,720,order);
    assert.equal(rows[3].history,rows[3].plan);
  }
});

test('lowest cover follows the minimum individual cover, with rolling product demand',()=>{
  assert.equal(operationalPoint(result,widget('lowest_cover'),products,health,0,null),1);
  assert.equal(operationalPoint(result,widget('lowest_cover'),products,health,1,null),.5);
  assert.match(render('lowest_cover'),/<svg/);
});

test('flow keys retain yesterday fallback and only one muted line',()=>{
  const html=render('demand',0,0);
  assert.match(html,/14 units/);assert.match(html,/Yesterday/);
  assert.equal((html.match(/<small>/g)||[]).length,1);
});

test('unknown product demand keeps stock keys in units instead of showing partial cover',()=>{
  const incomplete={...health,products:health.products.map((product,i)=>({...product,daily_demand:i?null:2}))};
  const html=renderToStaticMarkup(React.createElement(OperationalWidget,{widget:widget('on_hand'),products,health:incomplete,recordedHealth:incomplete,day:-1,minute:null,orderDate:order}));
  assert.match(html,/<strong[^>]*>14 units<\/strong>/);
});

test('sentence titles retain acronyms and order subtitle uses the actual order date',()=>{
  assert.equal(sentenceTitle('Value Strawberry Water Ices · Stock'),'Value strawberry water ices · stock');
  assert.equal(sentenceTitle('UK SKU · Fill Rate'),'UK SKU · fill rate');
  assert.equal(sentenceTitle('Regional Vanilla Availability'),'Regional vanilla availability');
  assert.equal(sentenceTitle('Chocolate-Coated · Requests'),'Chocolate-coated · requests');
  assert.equal(sentenceTitle('APAC SKU123 · Vanilla Availability'),'APAC SKU123 · vanilla availability');
  assert.equal(sentenceTitle('new seasonal availability'),'New seasonal availability');
  assert.equal(sentenceTitle('STOCK ON HAND'),'Stock on hand');
  assert.equal(orderDateLabel(order),'Mon 27 Jul');
  const props={detail:{plan:{week_start:order}},products,path:'/test'};
  const watch=renderToStaticMarkup(React.createElement(Dashboard,props));
  const play=renderToStaticMarkup(React.createElement(Dashboard,{...props,result,day:0}));
  assert.match(watch,/Up to the order on Mon 27 Jul/);
  assert.match(play,/Since the order on Mon 27 Jul/);
});
