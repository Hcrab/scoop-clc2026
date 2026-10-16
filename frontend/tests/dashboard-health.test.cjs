const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const Module=require('node:module');
const {test}=require('node:test');
const ts=require('typescript');
const loaded=new Map();
function load(name){
  const file=path.join(__dirname,'..','src',name);
  if(loaded.has(file))return loaded.get(file).exports;
  const mod=new Module(file,module);mod.filename=file;mod.paths=Module._nodeModulePaths(path.dirname(file));loaded.set(file,mod);
  const normal=mod.require.bind(mod);
  mod.require=id=>id.startsWith('./')?load(`${id.slice(2)}.ts`):normal(id);
  mod._compile(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,file);
  return mod.exports;
}
const {fillTone,countTone,capacityTone,rankedCover,lowCover,healthAtClock,stockEvidence}=load('dashboardHealth.ts');
const {widgetChartPoint,widgetDisplayPoint}=load('replayData.ts');
const product=(sku,cover,lead=3)=>({sku,name:sku,on_hand_units:20,daily_demand:10,days_cover:cover,lead_time_days:lead,recent_demand:Array(7).fill(10)});
const health={period_start:'2026-10-09',through:'2026-10-15',requested_units:100,shipped_units:98,fill_rate:.98,stockout_skus:['old'],stockout_sku_days:2,pallets:2,peak_pallets:3,capacity_pallets:5,products:[product('a',2),{...product('b',null),daily_demand:0,recent_demand:Array(7).fill(0)}]};
function replay(){
  const run={daily:[{pallets:1,pallets_pre_ship:3},{pallets:0,pallets_pre_ship:5}],per_sku:{on_hand:[[10,0],[0,0]],shipped:[[10,0],[10,0]],lost:[[0,0],[10,0]],arrived:[[0,0],[0,0]]},hourly:{}};
  const result={dates:['2026-10-16','2026-10-17'],skus:['a','b'],demand:[[10,0],[20,0]],intraday:{step_minutes:10,minutes:Array.from({length:145},(_,i)=>i*10),demand_cdf:Array.from({length:145},(_,i)=>i/144),dispatch_cdf:Array.from({length:145},(_,i)=>i<108?0:(i-107)/37),arrival_minutes:[[120,120],[120,120]],opening_on_hand:[20,0]},runs:{scoop:run},capacity_pallets:5};
  Object.defineProperty(result.runs,'baseline',{get(){throw Error('Watch/Play must not read baseline')}});
  return result;
}
const products=[{sku:'a',units_per_case:10,cases_per_pallet:1},{sku:'b',units_per_case:10,cases_per_pallet:1}];
const widget={metric:'demand',skus:['a'],series:[{date:'2026-10-15',value:8}],value:8};

test('exact KPI color thresholds are inclusive at each healthy boundary',()=>{
  assert.deepEqual([.949999,.95,.979999,.98,1].map(fillTone),['coral','amber','amber','green','green']);
  assert.deepEqual([0,1,3,4].map(countTone),['green','amber','amber','coral']);
  assert.deepEqual([94.999,95,95.001,100,100.001].map(p=>capacityTone(p,100)),['green','green','amber','amber','coral']);
  assert.equal(capacityTone(0,0),'green');assert.equal(capacityTone(1,0),'coral');
});
test('low cover uses strict supplier comparison, zero stock qualifies, null demand does not',()=>{
  const rows=[product('equal',3),product('none',null),product('zero',0),product('below',2.99),product('long',4,5),product('bad',NaN)];
  assert.deepEqual(lowCover(rows).map(p=>p.sku),['zero','below','long']);
  assert.deepEqual(rankedCover(rows).slice(0,5).map(p=>p.sku),['zero','below','equal','long']);
  assert.equal(rows[0].sku,'equal');
});
test('first simulated night keeps historical flows and numeric current stock without future peaks',()=>{
  const value=healthAtClock(health,replay(),products,0,0);
  assert.equal(value.fill_rate,.98);assert.equal(value.requested_units,100);
  assert.equal(value.pallets,2);assert.equal(value.peak_pallets,3);
  assert.equal(value.products[0].days_cover,2);assert.equal(value.products[1].days_cover,null);
  assert.deepEqual(widgetDisplayPoint(replay(),widget,products,0,0),{value:8,yesterday:true});
});
test('completed days accumulate Scoop totals; first night on day two uses completed yesterday',()=>{
  const value=healthAtClock(health,replay(),products,1,0);
  assert.equal(value.requested_units,110);assert.equal(value.shipped_units,108);
  assert.equal(value.pallets,1);assert.equal(value.peak_pallets,3);
  assert.equal(value.products[0].days_cover,1);
  assert.deepEqual(widgetDisplayPoint(replay(),widget,products,1,0),{value:10,yesterday:true});
  const end=healthAtClock(health,replay(),products,1,null);
  assert.equal(end.requested_units,130);assert.equal(end.shipped_units,118);
  assert.deepEqual(end.stockout_skus,['old','a']);assert.equal(end.stockout_sku_days,3);assert.equal(end.peak_pallets,5);
});
test('no demand preserves a usable fill ratio and excludes null cover from low stock count',()=>{
  const empty={...health,requested_units:0,shipped_units:0,fill_rate:1,products:[{...product('a',null),daily_demand:0,recent_demand:Array(7).fill(0)}]};
  const result=replay();result.demand=[[0,0],[0,0]];result.runs.scoop.per_sku.shipped=[[0,0],[0,0]];
  const value=healthAtClock(empty,result,products,0,1430);
  assert.equal(value.fill_rate,1);assert.deepEqual(lowCover(value.products),[]);
});
test('current point is absent before noon, then uses a full-day projection, keys use actual flows',()=>{
  const result=replay();
  assert.equal(widgetChartPoint(result,widget,products,0,710).value,null);
  assert.equal(widgetChartPoint(result,widget,products,0,720).value,10);
  assert.equal(widgetChartPoint(result,widget,products,0,1080).value,10);
  assert.equal(widgetDisplayPoint(result,widget,products,0,1080).value,7.5);
  assert.equal(widgetDisplayPoint(result,widget,products,0,1430).value,10);
});
test('safety stock protects to the next known receipt and uses trailing demand, without policy comparison',()=>{
  const result=replay();result.runs.scoop.per_sku.arrived[1][0]=20;result.intraday.arrival_minutes[1][0]=720;
  assert.deepEqual(stockEvidence(health,result,['a'],0,720),{dailyDemand:10,safeUnits:10});
  assert.deepEqual(stockEvidence(health,result,['b'],0,720),{dailyDemand:0,safeUnits:0});
});
