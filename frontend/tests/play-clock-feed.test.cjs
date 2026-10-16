const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const Module=require('node:module');
const {test}=require('node:test');
const ts=require('typescript');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const loaded=new Map(),dashboardProps=[];
function load(name){
  if(name==='Dashboard')return {Dashboard:props=>{dashboardProps.push(props);return null}};
  const base=path.join(__dirname,'..','src',name);
  const file=fs.existsSync(base)?base:['.ts','.tsx'].map(ext=>base+ext).find(file=>fs.existsSync(file));
  if(file.endsWith('.css'))return {};
  if(loaded.has(file))return loaded.get(file).exports;
  const mod=new Module(file,module);mod.filename=file;mod.paths=Module._nodeModulePaths(path.dirname(file));loaded.set(file,mod);
  const normal=mod.require.bind(mod);mod.require=id=>id.startsWith('./')?load(id.slice(2)):normal(id);
  mod._compile(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,file);
  return mod.exports;
}
const {formatPlayClock,PlayWeek}=load('Play');
const product={sku:'coffee',name:'Coffee Crunch Bar'};
const event=(id,date,minute,extra={})=>({id,date,minute,time:'12:40',kind:'arrival',tone:'good',sku:'coffee',text:'12 cases arrived',card_ids:['a','b'],...extra});
const result={days:3,dates:['2026-07-30','2026-07-31','2026-08-01'],events:[
  event('order','2026-07-30',0,{kind:'order',text:'Order placed',lines:[{...product,cases:12,order_date:'2026-07-30',expected_arrival:'2026-08-01',card_ids:['a','b']}]}),
  event('arrival','2026-08-01',760),
  event('future','2026-08-01',770,{text:'Future delivery'}),
]};
function render(patch={}){
  return renderToStaticMarkup(React.createElement(PlayWeek,{detail:{plan:{id:'test',week_start:'2026-07-30'}},products:[product],path:'/test',replay:{result,day:2,minute:760,running:false,unlocked:true,...patch},setReplay:()=>{},onSeeResults:()=>{}}));
}
test('clock shows actual weekday, date and time across month and year rollover',()=>{
  assert.equal(formatPlayClock('2026-07-29',760),'Wed 29 Jul · 12:40');
  assert.equal(formatPlayClock('2026-07-31',1430),'Fri 31 Jul · 23:50');
  assert.equal(formatPlayClock('2026-08-01',0),'Sat 1 Aug · 00:00');
  assert.equal(formatPlayClock('2027-01-01',5),'Fri 1 Jan · 00:05');
  assert.match(render(),/<strong>Sat 1 Aug · 12:40<\/strong><span>Day 3 since the order<\/span>/);
  assert.match(render({day:0,minute:0}),/Day 1 since the order/);
  assert.match(render({day:1,minute:1430}),/Day 2 since the order/);
});
test('feed retains grouped products, cases and arrival dates without decision captions',()=>{
  const html=render();
  assert.match(html,/<details class="play-order-details"><summary>Order placed<\/summary>/);
  assert.match(html,/<strong>Coffee Crunch Bar<\/strong><p>12 cases · expected 1 Aug<\/p>/);
  assert.match(html,/12 cases arrived/);
  assert.doesNotMatch(html,/Decision|Recorded|Simulated|Illustrative scenario|Simple rule|Future delivery/);
  assert.doesNotMatch(render({minute:759}),/12 cases arrived/);
  assert.doesNotMatch(render({day:1,minute:1430}),/12 cases arrived/);
  assert.equal(dashboardProps.at(-1).comparison,undefined);
  assert.equal(dashboardProps.at(-1).minute,1430);
});
test('normal playback and Results transition controls remain available',()=>{
  assert.match(render({running:true}),/>Pause<\/button>/);
  assert.match(render(),/>Resume<\/button>/);
  const complete=render({minute:1430});
  assert.match(complete,/>Replay<\/button>/);
  assert.match(complete,/>See results<\/button>/);
  assert.doesNotMatch(complete,/<button[^>]*disabled/);
  assert.match(render({minute:1430,unlocked:false}),/<button[^>]*disabled=""[^>]*>See results/);
});
