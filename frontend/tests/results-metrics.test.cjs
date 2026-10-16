const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const Module=require('node:module');
const {test}=require('node:test');
const ts=require('typescript');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');

function load(name){
  const file=path.join(__dirname,'..','src',name);
  const mod=new Module(file,module);mod.filename=file;mod.paths=Module._nodeModulePaths(path.dirname(file));
  const normal=mod.require.bind(mod);
  mod.require=id=>id==='./Dashboard'?{Dashboard:()=>null}:id==='./ProductIcon'?{}:id.startsWith('./')?load(`${id.slice(2)}.ts`):normal(id);
  mod._compile(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,file);
  return mod.exports;
}
const {resultsMetrics}=load('resultsMetrics.ts');
const {Results}=load('Play.tsx');
const summary={baseline:{lost_units:6063,stockout_sku_days:39,lost_margin:30849.110000000004},scoop:{lost_units:4297,stockout_sku_days:36,lost_margin:24271.33}};
const render=(values=summary)=>renderToStaticMarkup(React.createElement(Results,{result:{start:'2026-07-27',end:'2026-08-09',days:14,capacity_pallets:120,affected_skus:['a'],summary:values},detail:{},products:[{sku:'a',name:'Strawberry'}],path:'/test'}));

test('stored replay outcomes show both policies and rounded relative leads',()=>{
  const metrics=resultsMetrics(summary);
  assert.deepEqual(metrics.map(({title,rule,scoop,badge})=>({title,rule,scoop,badge})),[
    {title:'Units short',rule:6063,scoop:4297,badge:'29% fewer'},
    {title:'Stockout product-days',rule:39,scoop:36,badge:'8% fewer'},
    {title:'Lost margin',rule:30849.110000000004,scoop:24271.33,badge:'21% less'},
  ]);
  assert.equal(resultsMetrics({baseline:{lost_units:200},scoop:{lost_units:133}})[0].badge,'34% fewer');
  const html=render(),cards=[...html.matchAll(/<article class="result-metric">([^]*?)<\/article>/g)].map(match=>match[1]);
  assert.equal(cards.length,3);
  for(const [i,card] of cards.entries()){
    assert.ok(card.includes(metrics[i].title));
    assert.ok(card.includes('Simple rule'));assert.ok(card.includes('Scoop'));assert.ok(card.includes(metrics[i].badge));
  }
  for(const value of ['6,063','4,297','39','36','HK$30,849','HK$24,271'])assert.ok(html.includes(value));
  assert.ok(html.includes('Same cold store (120 pallets) · same store demand · Simple rule = 28-day average + 25%'));
  for(const label of ['Affected products','Strawberry','See full comparison'])assert.ok(html.includes(label));
  assert.doesNotMatch(html,/avoided|Illustrative scenario|Scoop plan peaks/);
});

test('equal and worse outcomes use nonnegative more badges and the coral class',()=>{
  const values={baseline:{lost_units:100,stockout_sku_days:10,lost_margin:0},scoop:{lost_units:100,stockout_sku_days:12,lost_margin:0}};
  assert.deepEqual(resultsMetrics(values).map(({badge,worse})=>({badge,worse})),[{badge:'0% more',worse:true},{badge:'20% more',worse:true},{badge:'0% more',worse:true}]);
  const html=render(values);
  assert.equal((html.match(/result-badge-worse/g)||[]).length,3);
  assert.doesNotMatch(html,/-\d+%/);
});

test('zero rule with positive Scoop loss never fabricates a finite percentage',()=>{
  const values={baseline:{lost_units:0,stockout_sku_days:0,lost_margin:0},scoop:{lost_units:1,stockout_sku_days:1,lost_margin:1}};
  assert.ok(resultsMetrics(values).every(metric=>metric.badge===null));
  assert.doesNotMatch(render(values),/result-badge|Infinity|NaN|\d+% more/);
});
