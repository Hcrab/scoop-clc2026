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
const {resultsStockData,ResultsStockChart}=load('ResultsStockChart');
const {WidgetChart}=load('Dashboard');
const run=stock=>({daily:stock.map(()=>({pallets:0,pallets_pre_ship:0})),per_sku:{on_hand:stock,shipped:[[2,1],[3,2]],lost:[[1,0],[0,1]],arrived:[[0,0],[0,0]]},hourly:{}});
const result=()=>({dates:['2026-10-16','2026-10-17'],skus:['a','b'],demand:[[3,1],[3,3]],runs:{scoop:run([[7,3],[4,1]]),baseline:run([[2,1],[1,0]])},intraday:{dispatch_cdf:[1],arrival_minutes:[[0,0],[0,0]]}});
const history=[{date:'2026-10-13',on_hand_units:20},{date:'2026-10-14',on_hand_units:null},{date:'2026-10-15',on_hand_units:15}];
const products=[{sku:'a',units_per_case:1,cases_per_pallet:10},{sku:'b',units_per_case:1,cases_per_pallet:10}];
const widget=metric=>({metric,skus:['a','b'],unit:metric==='fill_rate'?'ratio':metric==='days_cover'?'days':metric==='pallets'?'pallets':'units',series:[{date:'2026-10-15',value:15}],value:15,recent_demand:Array.from({length:7},(_,i)=>({date:`2026-10-${String(i+9).padStart(2,'0')}`,value:5}))});
const renderWidget=(metric,replay,comparison)=>renderToStaticMarkup(React.createElement(WidgetChart,{widget:widget(metric),result:replay,day:1,minute:null,products,comparison}));

test('warehouse paths use native closing stock totals and share only the last recorded anchor',()=>{
  const replay=result(),before=JSON.stringify(replay);
  const data=resultsStockData(replay,history);
  assert.ok(Number.isNaN(data[1].history));assert.ok(Number.isNaN(data[0].plan));
  assert.deepEqual([data[2].history,data[2].plan,data[2].rule],[15,15,15]);
  assert.deepEqual(data.slice(3).map(row=>[row.plan,row.rule]),[[10,3],[5,1]]);
  assert.equal(JSON.stringify(replay),before);
  assert.equal(resultsStockData(replay).length,2);
  assert.equal(resultsStockData(replay,[...history,{date:'2026-10-16',on_hand_units:99}]).length,5);
});

test('main Results overlay renders three named colors on one chart and equal values use equal coordinates',()=>{
  const replay=result();replay.runs.baseline=run([[7,3],[4,1]]);
  const html=renderToStaticMarkup(React.createElement(ResultsStockChart,{result:replay,history}));
  assert.equal((html.match(/<svg/g)||[]).length,1);
  for(const color of ['#9aa6a0','#205a4e','#b77d36'])assert.ok(html.includes(color));
  for(const label of ['Recorded history','Scoop plan','Simple rule'])assert.ok(html.includes(label));
  const points=key=>html.match(new RegExp(`data-series="${key}"><polyline[^>]*points="([^"]+)"`))[1];
  assert.equal(points('plan'),points('rule'));
});

test('default widget mode never accesses baseline across stock, flows, demand and cover list',()=>{
  const replay=result();Object.defineProperty(replay.runs,'baseline',{get(){throw Error('baseline accessed outside Results')}});
  for(const metric of ['on_hand','days_cover','pallets','fill_rate','lost_units','demand','requested_vs_expected','lowest_cover']){
    const html=renderWidget(metric,replay);
    assert.ok(!html.includes('Simple rule'));
  }
});

test('Results detailed policy widgets share one axis, keep policy colors and stock alert evidence',()=>{
  for(const metric of ['on_hand','days_cover','pallets','fill_rate','lost_units']){
    const html=renderWidget(metric,result(),true);
    assert.equal((html.match(/<svg/g)||[]).length,1);
    assert.ok(html.includes('data-series="rule"'));
    assert.ok(html.includes('stroke="#205a4e"'));
    assert.ok(html.includes('stroke="#b77d36"'));
  }
  const replay=result();replay.runs.scoop.per_sku.on_hand[0]=[0,0];
  const html=renderWidget('on_hand',replay,true);
  assert.ok(html.includes('data-series="stockout"'));
});

test('Results demand and lowest-cover widgets never access baseline',()=>{
  const replay=result();Object.defineProperty(replay.runs,'baseline',{get(){throw Error('demand must stay requested only')}});
  for(const metric of ['demand','requested_vs_expected','lowest_cover']){
    const html=renderWidget(metric,replay,true);
    assert.ok(!html.includes('Simple rule'));
    if(metric!=='lowest_cover')assert.ok(html.includes('#4e83b8'));
  }
});

test('only Results opts into dashboard comparison and retains the three outcomes and full comparison',()=>{
  const dashboard=load('Dashboard'),original=dashboard.Dashboard;
  const seen=[];
  dashboard.Dashboard=props=>{seen.push(props.comparison);return null};
  try{
    const {Results,PlayWeek}=load('Play');
    const summary={fill_rate:.9,lost_units:1,lost_margin:2,avg_pallets:3,peak_pallets:4,days_over_capacity:0,stockout_sku_days:1};
    const replay={...result(),start:'2026-10-16',end:'2026-10-17',days:2,events:[],affected_skus:[],summary:{scoop:summary,baseline:summary},capacity_pallets:10};
    const props={result:replay,detail:{plan:{id:'test',week_start:'2026-10-16'}},products,path:'/test'};
    const html=renderToStaticMarkup(React.createElement(Results,props));
    assert.deepEqual(seen,[true]);
    for(const label of ['Units short avoided','Stockout product-days avoided','Lost margin avoided','See full comparison'])assert.ok(html.includes(label));
    renderToStaticMarkup(React.createElement(PlayWeek,{...props,replay:{result:replay,day:0,minute:0,running:false,unlocked:false},setReplay:()=>{},onSeeResults:()=>{}}));
    assert.deepEqual(seen,[true,undefined]);
  }finally{dashboard.Dashboard=original}
});
