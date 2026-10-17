const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const Module=require('node:module');
const ts=require('typescript');
const file=path.resolve(__dirname,'../src/tour/copy.ts');
const mod=new Module(file,module);
mod._compile(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,file);
const {TOUR_COPY:copy,fillTourCopy}=mod.exports;
const protocol=fs.readFileSync(path.resolve(__dirname,'../../docs/reports/tour-v2-protocol.md'),'utf8');
const string=(block,label)=>block.match(new RegExp('^- '+label+': `([^`]+)`','m'))?.[1];

test('all fourteen title/body entries match the supplied protocol verbatim, including bold',()=>{
  const blocks=[...protocol.matchAll(/\*\*Step (\d+) of 14[\s\S]*?(?=\n\*\*(?:Step \d+ of 14|End \(modal\)))/g)];
  assert.equal(blocks.length,14);
  for(const match of blocks){
    const step=Number(match[1]),block=match[0];
    assert.equal(copy.steps[step].title,string(block,'Title'),`Step ${step} title`);
    const body=string(block,'Body');
    if(body&&step!==11)assert.equal(copy.steps[step].body,body,`Step ${step} body`);
    if(step===11)assert.equal(copy.steps[step].body,body.replace('Add one more card to follow.','Choose the cards to add.'));
  }
});

test('welcome/end and question, context and widget choices preserve final copy',()=>{
  const welcome=protocol.split('**Welcome (modal)**')[1].split('**Step 1 of 14')[0];
  const end=protocol.split('**End (modal)**')[1].split('## V5')[0];
  for(const [name,block] of [['welcome',welcome],['end',end]]){
    assert.equal(copy[name].title,string(block,'Title'));assert.equal(copy[name].body,string(block,'Body'));
    assert.ok(block.includes('`'+copy[name].explore+'`'));
  }
  for(const item of [...Object.values(copy.questions),...Object.values(copy.contexts),...Object.values(copy.widgets),copy.next,copy.skip,copy.welcome.start,copy.end.replay])assert.ok(protocol.includes('`'+item+'`')||protocol.includes('**'+item+'**'),item);
});

test('branch copy only omits the explicitly optional no-capacity-cut sentence',()=>{
  const block=protocol.split('**Step 7 of 14')[1].split('**Step 8 of 14')[0];
  assert.equal(copy.recalculation.summer,string(block,'Body, one-off branch'));
  assert.equal(copy.recalculation.growingWithCut,string(block,'Body, keep-growing branch'));
  const cut='To stay within the cold store, it trims **{n} cases** from lower-value lines. ';
  assert.equal(copy.recalculation.growing,copy.recalculation.growingWithCut.replace(cut,''));
  assert.equal(copy.recalculation.unchanged,string(block,'Body, nothing-to-add branch'));
  for(const event of [copy.events.heat,copy.events.arrival,copy.events.stockout,copy.events.endBody])assert.ok(protocol.includes('`'+event+'`'));
  assert.equal(fillTourCopy(copy.steps[2].body,{effect:38}),'The first finding: value strawberry water ices are selling **38% above forecast**.');
});


test('tour revision adds the exact future notice and multi-select action without changing branch arithmetic copy',()=>{
  assert.equal(copy.futureNotice,'In this tour, the next two weeks follow the context you chose.');
  assert.equal(copy.addSelected,'Add selected');
  assert.ok(!copy.steps[11].body.includes('Add one more card'));
  assert.match(copy.recalculation.growingWithCut,/\{n\} cases/);
  assert.ok(!copy.recalculation.growing.includes('trims'));
});
