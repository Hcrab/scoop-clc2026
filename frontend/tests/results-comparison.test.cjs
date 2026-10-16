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
const {operationalData,operationalPoint}=load('OperationalWidget');
const {DashboardKpis}=load('DashboardKpis');
const run=stock=>({daily:stock.map(()=>({pallets:0,pallets_pre_ship:0})),per_sku:{on_hand:stock,shipped:[[2,1],[3,2]],lost:[[1,0],[0,1]],arrived:[[0,0],[0,0]]},hourly:{}});
const result=()=>({dates:['2026-10-16','2026-10-17'],skus:['a','b'],demand:[[3,1],[3,3]],runs:{scoop:run([[7,3],[4,1]]),baseline:run([[2,1],[1,0]])},intraday:{dispatch_cdf:Array(145).fill(1),demand_cdf:Array(145).fill(1),minutes:Array.from({length:145},(_,i)=>i*10),opening_on_hand:[10,5],arrival_minutes:[[0,0],[0,0]]}});
const history=[{date:'2026-10-13',on_hand_units:20},{date:'2026-10-14',on_hand_units:null},{date:'2026-10-15',on_hand_units:15}];
const products=[{sku:'a',units_per_case:1,cases_per_pallet:10},{sku:'b',units_per_case:1,cases_per_pallet:10}];
const widget=metric=>({metric,skus:['a','b'],unit:metric==='fill_rate'?'ratio':['days_cover','lowest_cover'].includes(metric)?'days':metric==='pallets'?'pallets':'units',series:[{date:'2026-10-15',value:15}],value:15,recent_demand:Array.from({length:7},(_,i)=>({date:`2026-10-${String(i+9).padStart(2,'0')}`,value:5}))});
const renderWidget=(metric,replay,comparison,day=1)=>renderToStaticMarkup(React.createElement(WidgetChart,{widget:widget(metric),result:replay,day,minute:null,products,comparison}));

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
  for(const label of ['Before the order','Scoop plan','Simple rule'])assert.ok(html.includes(label));
  const points=key=>html.match(new RegExp(`data-series="${key}"><polyline[^>]*points="([^"]+)"`))[1];
  assert.equal(points('plan'),points('rule'));
});

test('Watch and Play never access baseline for any metric',()=>{
  const replay=result();Object.defineProperty(replay.runs,'baseline',{get(){throw Error('baseline accessed outside Results')}});
  for(const metric of ['on_hand','days_cover','pallets','fill_rate','lost_units','demand','requested_vs_expected','lowest_cover']){
    for(const day of [-1,1]){
      const html=renderWidget(metric,replay,false,day);
      assert.ok(!html.includes('Simple rule'));
    }
  }
});

test('every Results metric uses the operational chart with only history and two policies',()=>{
  for(const metric of ['on_hand','days_cover','pallets','fill_rate','lost_units','demand','requested_vs_expected','lowest_cover']){
    const health={products:products.map(p=>({...p,daily_demand:2,recent_demand:Array(7).fill(2)}))};
    const html=renderToStaticMarkup(React.createElement(WidgetChart,{widget:widget(metric),result:result(),day:1,minute:null,products,health,recordedHealth:health,comparison:true}));
    assert.equal((html.match(/<svg/g)||[]).length,1);
    const svg=html.match(/<svg[^]*?<\/svg>/)[0];
    assert.deepEqual([...svg.matchAll(/data-series="([^"]+)"/g)].map(m=>m[1]),['history','plan','rule']);
    for(const label of ['Before the order','Scoop plan','Simple rule','Source data','Order placed'])assert.ok(html.includes(label));
    assert.doesNotMatch(html,/Recorded|Simulated|Requested|risk|Safety|Safe zone|Stockout|data-band|cover-list/);
    for(const color of ['#9aa6a0','#205a4e','#b77d36'])assert.ok(svg.includes(color));
    assert.ok((html.match(/<small>/g)||[]).length<=1);
  }
});

test('Results lowest cover uses actual stock for each policy and rolling per-product demand',()=>{
  const replay=result(),health={products:products.map((p,i)=>({...p,daily_demand:i?2:1,recent_demand:Array(7).fill(i?2:1)}))};
  const w=widget('lowest_cover');
  assert.equal(operationalPoint(replay,w,products,health,0,null,'scoop'),1.5);
  assert.equal(operationalPoint(replay,w,products,health,0,null,'baseline'),.5);
  const rows=operationalData(w,replay,products,health,1,null,replay.dates[0],true);
  assert.deepEqual([rows[1].plan,rows[1].rule],[1.5,.5]);
  assert.equal(rows[2].plan,1/(13/7));assert.equal(rows[2].rule,0);
});

test('comparison charts retain missing history, morning gaps and hollow noon projections for both policies',()=>{
  for(const metric of ['on_hand','days_cover','pallets','fill_rate','lost_units','demand','requested_vs_expected','lowest_cover']){
    const replay=result(),health={products:products.map(p=>({...p,recent_demand:Array(7).fill(2)}))};
    const w={...widget(metric),series:[{date:'2026-10-14',value:null},{date:'2026-10-15',value:15}]};
    const rows=operationalData(w,replay,products,health,1,710,replay.dates[0],true);
    assert.ok(Number.isNaN(rows[0].history));assert.ok(Number.isNaN(rows.at(-1).plan));assert.ok(Number.isNaN(rows.at(-1).rule));
    const props={widget:w,result:replay,day:1,products,recordedHealth:health,comparison:true};
    const morning=renderToStaticMarkup(React.createElement(WidgetChart,{...props,minute:710}));
    const noon=renderToStaticMarkup(React.createElement(WidgetChart,{...props,minute:720}));
    assert.doesNotMatch(morning,/data-partial="true"/);
    assert.equal((noon.match(/data-partial="true"/g)||[]).length,2);
    assert.match(noon,/fill="var\(--paper, #fff\)"/);
  }
});

test('fill tile keeps only its period line with unchanged numeric value',()=>{
  const health={fill_rate:.98,shipped_units:98,requested_units:100,period_start:'2026-07-13',stockout_skus:[],stockout_sku_days:0,products:[],pallets:0,peak_pallets:0,capacity_pallets:5};
  for(const sinceOrder of [false,true]){
    const html=renderToStaticMarkup(React.createElement(DashboardKpis,{health,orderDate:'2026-07-27',sinceOrder,flowYesterday:true}));
    const tile=html.slice(html.indexOf('<span>Fill rate</span>'),html.indexOf('<span>Stockouts</span>'));
    assert.match(tile,/98%/);assert.equal((tile.match(/<small>/g)||[]).length,1);
    assert.ok(tile.includes(sinceOrder?'since 27 Jul':'14 days before 27 Jul'));
    assert.doesNotMatch(tile,/of store requests|through yesterday/);
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
