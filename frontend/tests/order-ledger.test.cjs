const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const { test } = require('node:test');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');

const file = path.resolve(__dirname, '../src/OrderLedger.tsx');
const mod = new Module(file, module);
mod.filename = file; mod.paths = Module._nodeModulePaths(path.dirname(file));
mod._compile(ts.transpileModule(fs.readFileSync(file, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText, file);
const { OrderLedger } = mod.exports;
const base = {days:14,in_stock_target_percent:98,forecast_units:100,safety_units:20,rounding_units:0,target_units:120,stock_units:20,transit_units:4,net_units:96,need_units:96,surplus_units:0,units_per_case:12,packed_cases:8,minimum_added_cases:0,capacity_removed_cases:0,case_adjustment:0,quantity_edited:false,effective_cases:8,trend:null};
const render = (changes={},quantityPending=false) => renderToStaticMarkup(React.createElement(OrderLedger,{ledger:{...base,...changes},quantityPending}));

test('renders aligned whole-unit ledger with plain labels and conditional trend', () => {
  const text=render();
  for (const label of ['How we got 8 cases','Expected sales over the next 14 days','Safety buffer for the 98% in-stock target','Already in the cold store','Already on the way','96 units → 8 cases','12 per case']) assert.ok(text.includes(label),label);
  assert.ok(text.includes('<dl>'));
  assert.ok(!/p50|protection period|service point|position|trend|supplier minimum|Trimmed/.test(text));
  assert.match(render({trend:{percent:38.1,name:'Strawberry'}}),/incl\. \+38\.1% Strawberry trend/);
  assert.match(render({trend:{percent:-10,name:'Strawberry'}}),/incl\. −10% Strawberry trend/);
});

test('shows only applied case changes, preserves surplus and explains stale edits', () => {
  assert.match(render({minimum_added_cases:2,effective_cases:10}),/Rounded up to the supplier minimum/);
  assert.match(render({capacity_removed_cases:3,effective_cases:5}),/Trimmed to fit the cold store/);
  const edited=render({case_adjustment:-8,quantity_edited:true,effective_cases:0});
  assert.match(edited,/Your quantity adjustment/);
  assert.match(edited,/−8 cases/);
  assert.ok(!edited.includes('supplier minimum'));
  assert.match(render({},true),/Quantity change awaiting save or refresh\. This calculation shows 8 cases\./);
  assert.match(render({net_units:-34,need_units:0,surplus_units:34,packed_cases:0,effective_cases:0}),/no extra units are needed/);
  assert.match(render({rounding_units:1}),/Whole-unit rounding/);
});
