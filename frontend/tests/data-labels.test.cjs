const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),Module=require('node:module');
const {test}=require('node:test'),ts=require('typescript'),React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const loaded=new Map();
function load(name){
 const base=path.join(__dirname,'../src',name),file=fs.existsSync(base)?base:['.ts','.tsx'].map(ext=>base+ext).find(fs.existsSync);
 if(loaded.has(file))return loaded.get(file).exports;
 const mod=new Module(file,module);mod.filename=file;mod.paths=Module._nodeModulePaths(path.dirname(file));loaded.set(file,mod);const normal=mod.require.bind(mod);
 mod.require=id=>id.startsWith('./')?load(id.slice(2)):normal(id);
 mod._compile(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,file);return mod.exports;
}
const {labelledEvidence}=load('dataLabels'),{DataView}=load('ui');
const fields={demand_p50:2348,inventory_position:1205,dc_protection_period:{p50:123,protection_period:11,service_point:98},other:[{position:6}]};
test('human-facing evidence labels and saved-result keys use business terms without changing values',()=>{
 const output=renderToStaticMarkup(React.createElement(DataView,{value:fields}));
 assert.doesNotMatch(output,/\bp50\b|protection period|service point|\bposition\b/i);
 assert.match(output,/Expected sales/);assert.match(output,/Stock on hand and on the way/);assert.match(output,/2,348/);
 const named=labelledEvidence(fields);assert.doesNotMatch(JSON.stringify(named),/\bp50\b|protection_period|service_point|\bposition\b/i);
 assert.equal(named['Expected sales'],2348);assert.equal(named.other[0]['Stock on hand and on the way'],6);assert.equal(fields.demand_p50,2348);
});
test('field display names do not filter or rewrite free natural-language answers',()=>{
 const response={reply:'A new observation can be described in any natural wording.',values:[2,3]};
 assert.deepEqual(labelledEvidence(response),response);
});
