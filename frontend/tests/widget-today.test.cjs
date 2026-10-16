const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const { test } = require('node:test');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');

const src = path.join(__dirname, '..', 'src');
const loaded = new Map();
function load(name) {
  const file = path.join(src, name);
  if (loaded.has(file)) return loaded.get(file).exports;
  const source = fs.readFileSync(file, 'utf8');
  const compiled = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
    jsx: ts.JsxEmit.ReactJSX,
  } }).outputText;
  const mod = new Module(file, module);
  mod.filename = file;
  mod.paths = Module._nodeModulePaths(path.dirname(file));
  loaded.set(file, mod);
  const normalRequire = mod.require.bind(mod);
  mod.require = id => id.startsWith('./') ? load(`${id.slice(2)}${id === './ui' ? '.tsx' : '.ts'}`) : normalRequire(id);
  mod._compile(compiled, file);
  return mod.exports;
}

const { widgetPoint } = load('replayData.ts');
const { Chart } = load('ui.tsx');
const cdf = Array.from({ length: 145 }, (_, slot) => slot < 5 ? slot * .1 : slot < 12 ? .5 + (slot - 5) * .015 : slot < 108 ? Math.min(1, .6 + (slot - 12) * .004) : 1);
const dispatch = Array.from({ length: 145 }, (_, slot) => slot < 108 ? 0 : (slot - 107) / 37);
const perSku = { on_hand: [[1]], shipped: [[7]], lost: [[5]], arrived: [[5]] };
const hourly = { on_hand: [], on_hand_delta: [], demand: [], shipped: [], lost: [], arrived: [] };
const run = { daily: [{ pallets_pre_ship: 0, pallets: 0 }], per_sku: perSku, hourly };
const result = {
  dates: ['2026-10-16'], skus: ['sku'], demand: [[10]],
  intraday: { step_minutes: 10, minutes: Array.from({ length: 145 }, (_, slot) => slot * 10), demand_cdf: cdf, dispatch_cdf: dispatch, arrival_minutes: [[120]], opening_on_hand: [3] },
  runs: { scoop: run, baseline: run }, capacity_pallets: 5,
};
const widget = metric => ({ metric, skus: ['sku'], unit: 'units', recent_demand: [] });
const point = (metric, minute) => widgetPoint(result, widget(metric), 'scoop', [], 0, minute).value;

test('today uses growing cumulative requests, then closes to raw daily totals', () => {
  assert.equal(point('demand', 50), 5);
  assert.ok(point('demand', 60) > point('demand', 50));
  assert.notEqual(point('demand', 60), point('demand', 60) - point('demand', 50));
  assert.equal(point('demand', 1430), 10);
  assert.equal(point('demand', null), 10);
  assert.equal(point('lost_units', 1430), perSku.lost[0][0]);
});

test('fill rate stays pending before dispatch and uses actual cumulative quantities afterward', () => {
  assert.equal(point('fill_rate', 50), null);
  assert.equal(point('fill_rate', 1070), null);
  assert.equal(point('fill_rate', 1080), 7 * dispatch[108] / (10 * cdf[108]));
  assert.equal(point('fill_rate', 1430), .7);
});

test('cumulative shortage cannot fall when stock arrives', () => {
  assert.equal(point('lost_units', 50), 2);
  assert.equal(point('lost_units', 120), point('lost_units', 110));
  assert.ok(point('lost_units', 120) >= point('lost_units', 50));
  assert.ok(point('lost_units', 130) >= point('lost_units', 120));
});

test('partial last chart value remains a hollow marker outside connected lines', () => {
  const data = [
    { date: '2026-10-14', plan: 40 },
    { date: '2026-10-15', plan: 50 },
    { date: '2026-10-16', plan: 5 },
  ];
  const props = { data, lines: [{ key: 'plan', label: 'This plan', color: '#205a4e' }], plotWidth: 400 };
  const partial = renderToStaticMarkup(React.createElement(Chart, { ...props, partialLast: true }));
  const historical = renderToStaticMarkup(React.createElement(Chart, props));
  assert.match(partial, /data-partial="true"/);
  assert.match(partial, /today so far, incomplete/);
  assert.equal((partial.match(/<polyline /g) || []).length, 1);
  assert.equal(partial.match(/<polyline [^>]*points="([^"]+)"/)[1].trim().split(/\s+/).length, 2);
  assert.equal((historical.match(/data-partial="true"/g) || []).length, 0);
  assert.equal(historical.match(/<polyline [^>]*points="([^"]+)"/)[1].trim().split(/\s+/).length, 3);
});

test('projected stockout points stay hollow and absent before the noon projection',()=>{
  const lines=[{key:'plan',label:'Scoop plan',color:'#205a4e'},{key:'stockout',label:'Stockout',color:'#c96c59',dots:true}];
  const data=[{date:'2026-10-15',plan:20,stockout:NaN},{date:'2026-10-16',plan:0,stockout:0}];
  const html=renderToStaticMarkup(React.createElement(Chart,{data,lines,partialLast:true,partialLabel:'Projected full day',plotWidth:400}));
  assert.match(html,/Projected full day/);
  assert.equal((html.match(/data-partial="true"/g)||[]).length,2);
  assert.match(html,/data-series="stockout"[^]*fill="var\(--paper, #fff\)"/);
  const night=renderToStaticMarkup(React.createElement(Chart,{data:[data[0],{...data[1],plan:NaN,stockout:NaN}],lines,partialLast:true,plotWidth:400}));
  assert.doesNotMatch(night,/data-partial="true"/);
});
