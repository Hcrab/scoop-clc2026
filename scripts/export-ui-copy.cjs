#!/usr/bin/env node
/* Read-only UI copy inventory. Run: node scripts/export-ui-copy.cjs
 * Existing frontend TypeScript and local Python are the only dependencies.
 * No app imports, browser, provider calls, writes to the service, or DB access.
 * Source ids address file + syntax position + role, not wording. Runtime sample
 * ids address GET endpoint + JSON pointer / HTML text-node position. Source rows
 * are editable copy; runtime rows are current examples, not source replacements.
 * --offline exports source only. --base-url http://127.0.0.1:8008 overrides GETs.
 */
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { spawnSync } = require('node:child_process');
const root = path.resolve(__dirname, '..');
const ts = require(path.join(root, 'frontend/node_modules/typescript'));
const rows = new Map();
const screens = {
  App: 'Workspace / Plans / Stores / Catalog / Evaluation / Settings',
  PlanSections: 'Discover / Discussion / Recap', ActionList: 'Orders', EditReceipt: 'Orders / edit receipt',
  Play: 'Play / Results', Dashboard: 'Watch', DashboardKpis: 'Watch / warehouse metrics',
  OperationalWidget: 'Watch / widgets', CohortCards: 'Discover / demand groups', CohortDrilldown: 'Demand group details',
  GeneratedReport: 'Discover / AI report', nativeReportCards: 'Discover / AI report actions',
  reportInteractions: 'Discover / AI report interactions', reportCharts: 'Discover / AI report charts',
  TrendExplorer: 'Discover / Trend explorer', EvidenceModal: 'Evidence', evidence: 'Evidence', ResultsStockChart: 'Results / stock chart',
  ProductIcon: 'Product illustrations', productVisuals: 'Catalog / product illustrations', ui: 'Shared UI', api: 'Shared errors / number and date formatting',
  chartTicks: 'Shared chart labels', dashboardHealth: 'Watch / warehouse health', replayData: 'Play / event feed',
  TourHost: 'Guided tour / welcome', GuidedTour: 'Guided tour / coach', copy: 'Guided tour / final copy', runtime: 'Guided tour / validation',
};
function add(file, position, role, text, screen, component) {
  if (typeof text !== 'string' || !text.trim()) return;
  const key = `${file}:${position}:${role}`;
  rows.set(key, { id: `ui-${crypto.createHash('sha256').update(key).digest('hex').slice(0,16)}`, screen,
    'component/file': `${file}:${position} [${component || role}; ${role}]`, 'current text': text });
}
const humanKeys = /^(?:label|title|text|message|description|summary|caption|placeholder|alt|name|unit|partialLabel|reason|note|hint|emptyText|aria-label|aria-description|aria-valuetext)$/;
const technicalAttrs = /^(?:className|class|style|key|id|type|role|href|src|srcDoc|d|fill|stroke|strokeWidth|strokeDasharray|viewBox|width|height|color|colorKey|icon|tone|name|value|scope|target|rel|sandbox|referrerPolicy|tabIndex|method|data-.*|aria-(?:hidden|expanded|controls|pressed|modal|live|atomic|busy|labelledby|describedby))$/;
function looksHuman(s) {
  if (!s.trim() || s.length > 3000 || /(?:<\/?[a-z]|=>|\b(?:SELECT|INSERT|UPDATE|DELETE|CREATE)\b|\{[^}]*:|querySelector|^https?:|^\/?(?:api|plans|products)\/|^#[\da-f]{3,8}$)/i.test(s)) return false;
  if (/^[\w.-]+\.(?:css|tsx?|json|csv|webp|png|svg)$/.test(s) || /^[-\w]+\/[\w.+-]+$/.test(s)) return false;
  return /[A-Za-z]/.test(s) && (/\s/.test(s) || /^[A-Z][a-z]+(?:[.!?…])?$/.test(s));
}
function componentOf(node) {
  for (let n = node; n; n = n.parent) {
    if ((ts.isFunctionDeclaration(n) || ts.isMethodDeclaration(n)) && n.name) return n.name.getText();
    if (ts.isVariableDeclaration(n) && (ts.isArrowFunction(n.initializer || {}) || ts.isFunctionExpression(n.initializer || {}))) return n.name.getText();
  }
  return 'module';
}
function exportTs(file, source, positionPrefix = '') {
  const sf = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, file.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
  const screen = screens[path.basename(file).replace(/\.[^.]+$/, '')] || 'Shared UI';
  const emitted = new Set();
  function emit(node, role, value) {
    const pos = node.getStart(sf), lc = sf.getLineAndCharacterOfPosition(pos);
    emitted.add(pos);
    add(file, `${positionPrefix}${lc.line+1}:${lc.character+1}`, role, value, screen, componentOf(node));
  }
  function value(node) { return ts.isStringLiteralLike(node) ? node.text : ts.isTemplateExpression(node) ? node.getText(sf).slice(1,-1) : `{${node.getText(sf)}}`; }
  function hasJsx(node) { let found = false; function v(n) { if(ts.isJsxElement(n)||ts.isJsxSelfClosingElement(n)||ts.isJsxFragment(n)) found=true; else ts.forEachChild(n,v); } v(node); return found; }
  function visit(node) {
    if(ts.isCallExpression(node)) {
      const callee=node.expression.getText(sf);let copy;
      if(/(?:^|\.)(?:button)$/.test(callee))copy=node.arguments[0];
      if(callee==='element')copy=node.arguments[1];
      if(/\.setAttribute$/.test(callee)&&node.arguments[0]&&/^(?:aria-label|aria-description|title|alt|placeholder)$/.test(node.arguments[0].text||''))copy=node.arguments[1];
      if(copy&&!ts.isArrowFunction(copy)&&!ts.isIdentifier(copy)&&copy.getText(sf).length<1800)emit(copy,'DOM copy template',value(copy));
    }
    if(ts.isBinaryExpression(node)&&node.operatorToken.kind===ts.SyntaxKind.EqualsToken&&/\.(?:textContent|innerText)$/.test(node.left.getText(sf)))emit(node.right,'DOM text template',value(node.right));
    if (ts.isJsxText(node)) {
      // React's JSX whitespace folding: line edges fold, deliberate inline spaces stay.
      const lines=node.text.replace(/\r/g,'').split('\n');
      const text=lines.map((s,i)=>i===0?s.trimEnd():i===lines.length-1?s.trimStart():s.trim()).filter(Boolean).join(' ');
      if(text.trim()) emit(node,'JSX text',decode(text));
    }
    if(ts.isJsxExpression(node) && node.expression && !ts.isJsxAttribute(node.parent) && !hasJsx(node.expression)) {
      const expr=node.expression;
      // These are the actual render expressions, including variable record labels.
      if(expr.getText(sf).length < 1800) emit(expr,'rendered template',value(expr));
    }
    if(ts.isJsxAttribute(node) && node.initializer && !technicalAttrs.test(node.name.getText(sf)) && !/^on[A-Z]/.test(node.name.getText(sf))) {
      const name=node.name.getText(sf);
      if(humanKeys.test(name) || /^aria-/.test(name)) {
        const expr=ts.isJsxExpression(node.initializer)?node.initializer.expression:node.initializer;
        if(expr)emit(expr,`${name} attribute`,value(expr));
      }
    }
    if(ts.isStringLiteralLike(node) || ts.isTemplateExpression(node)) {
      const parent=node.parent, text=value(node);
      let excluded=false;
      for(let p=parent;p&&!ts.isStatement(p);p=p.parent) {
        if(ts.isJsxAttribute(p) && (technicalAttrs.test(p.name.getText(sf))||/^on[A-Z]/.test(p.name.getText(sf)))) { excluded=true; break; }
        if(ts.isPropertyAssignment(p) && /^(?:color|colorKey|className|style|key|id|kind|type|role|method|icon|tone|sku|brand|src|path|url|status)$/.test(p.name.getText(sf).replace(/['"]/g,''))) { excluded=true; break; }
      }
      if(ts.isImportDeclaration(parent)||ts.isExportDeclaration(parent)||ts.isLiteralTypeNode(parent)||ts.isTemplateSpan(parent)||ts.isElementAccessExpression(parent)&&parent.argumentExpression===node||ts.isPropertyAssignment(parent)&&parent.name===node)excluded=true;
      if(ts.isBinaryExpression(parent) && [ts.SyntaxKind.EqualsEqualsEqualsToken,ts.SyntaxKind.ExclamationEqualsEqualsToken,ts.SyntaxKind.EqualsEqualsToken,ts.SyntaxKind.ExclamationEqualsToken].includes(parent.operatorToken.kind))excluded=true;
      if(/(?:T00:00:00Z|default-src|prefers-reduced-motion)/.test(text))excluded=true;
      for(let p=parent;p&&!ts.isStatement(p);p=p.parent) {
        if(ts.isCallExpression(p)&&/\.(?:querySelector(?:All)?|matches|closest|matchMedia|split|includes|startsWith|endsWith|addEventListener|removeEventListener)$/.test(p.expression.getText(sf))&&p.arguments.includes(node))excluded=true;
        if(ts.isJsxAttribute(p)&&/^(?:points|x|y|x1|x2|y1|y2|cx|cy|r|rx|strokeLinecap|strokeLinejoin|textAnchor)$/.test(p.name.getText(sf)))excluded=true;
      }
      if(!excluded && !emitted.has(node.getStart(sf)) && looksHuman(text))emit(node,'copy literal / template',text);
      if(ts.isPropertyAssignment(parent)&&parent.initializer===node&&humanKeys.test(parent.name.getText(sf).replace(/['"]/g,''))&&!excluded&&!emitted.has(node.getStart(sf)))emit(node,'display field',text);
      // Host-owned report bridge is JavaScript stored inside a tagged template.
      if(ts.isTaggedTemplateExpression(parent) && parent.tag.getText(sf)==='String.raw' && text.includes('document.')) {
        const embedded=text.replace(/\$\{payload\}/g,'null');
        exportTs(file,embedded,`${sf.getLineAndCharacterOfPosition(node.getStart(sf)).line+1}:embedded/`);
      }
    }
    ts.forEachChild(node,visit);
  }
  visit(sf);
}

function decode(s) { return s.replace(/&(#x[\da-f]+|#\d+|amp|lt|gt|quot|apos|nbsp|ndash|mdash|hellip|middot);/gi, (all,x)=> x[0]==='#'?String.fromCodePoint(x[1].toLowerCase()==='x'?parseInt(x.slice(2),16):parseInt(x.slice(1),10)):({amp:'&',lt:'<',gt:'>',quot:'"',apos:"'",nbsp:'\u00a0',ndash:'–',mdash:'—',hellip:'…',middot:'·'})[x.toLowerCase()]||all); }
function exportHtml(file,html,screen) {
  const tokens=html.matchAll(/<!--[\s\S]*?-->|<[^>]+>|[^<]+/g);
  let hidden=null,index=0;
  const stack=[];
  for(const match of tokens) {
    const token=match[0];
    if(/^<!--/.test(token))continue;
    const close=token.match(/^<\/([\w-]+)/),open=token.match(/^<([\w-]+)/);
    if(close){if(hidden===close[1].toLowerCase())hidden=null;const at=stack.lastIndexOf(close[1].toLowerCase());if(at>=0)stack.splice(at);continue;}
    if(open){const tag=open[1].toLowerCase();if(/^(script|style|template|noscript)$/.test(tag))hidden=tag;
      if(!hidden)for(const a of token.matchAll(/\b(title|alt|placeholder|aria-label|aria-description)\s*=\s*(["'])([\s\S]*?)\2/gi))add(file,`html@${match.index}:${a.index}`,'HTML attribute',decode(a[3]),screen,tag);
      if(!/^(?:meta|link|img|input|br|hr|source)$/.test(tag)&&!token.endsWith('/>'))stack.push(tag);continue;}
    if(hidden)continue;
    const text=decode(token).replace(/\s+/g,' ').trim();
    if(text)add(file,`text-node-${++index}@${match.index}`,'HTML visible text',text,screen,stack.join(' > '));
  }
}

// Python AST follows response/display fields, exceptions surfaced by the API,
// named label maps, narrator return copy, and play events. No prompts/SQL/docs.
const pythonExtractor = String.raw`
import ast,json,pathlib,re,sys
root=pathlib.Path(sys.argv[1]); rows=[]
keys={'label','title','text','message','description','summary','caption','reason','note','name','explanation','notice','display','magnitude','findings','watch_next','interpretation','recommendation'}
modules=['api','dashboard.py','monitoring.py','play.py','planning.py','workflow.py','discussion.py','demo_worlds.py','demo_reset.py','demo_gate.py','simulation_jobs.py','cohort_cards.py','cohort_context.py','algorithms/trend_scan.py','ai/narrator.py','ai/weekly.py','ai/investigator.py','ai/chat.py','ai/scenarios.py','ai/exploration_tools.py']
def text(n,src):
 if isinstance(n,ast.Constant) and isinstance(n.value,str):return n.value
 if isinstance(n,ast.JoinedStr):
  parts=[]
  for part in n.values:
   if isinstance(part,ast.Constant):parts.append(part.value)
   elif isinstance(part,ast.FormattedValue):
    expr=ast.get_source_segment(src,part.value) or ast.unparse(part.value)
    conversion='!'+chr(part.conversion) if part.conversion!=-1 else ''
    spec=':'+text(part.format_spec,src) if part.format_spec else ''
    parts.append('{'+expr+conversion+spec+'}')
  return ''.join(parts)
 return None
def human(s):return bool(s and re.search('[A-Za-z]',s) and (re.search(r'\s',s) or re.match(r'^[A-Z][a-z]+$',s)) and not re.search(r'(?i)\b(?:SELECT|INSERT|UPDATE|CREATE|DELETE|DROP|ALTER)\b|<[^>]+>|^https?://',s) and len(s)<2500)
for module in modules:
 base=root/'backend/scoop'/module
 files=sorted(base.rglob('*.py')) if base.is_dir() else [base]
 for file in files:
  if not file.exists():continue
  src=file.read_text(encoding='utf-8-sig');tree=ast.parse(src);parents={child:node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}; chosen={}
  def emit(n,role):
   ancestor=n
   while ancestor in parents:
    ancestor=parents[ancestor]
    if isinstance(ancestor,ast.Dict):
     fields={k.value:v for k,v in zip(ancestor.keys,ancestor.values) if isinstance(k,ast.Constant)}
     if 'role' in fields or 'parameters' in fields or 'parametersJsonSchema' in fields or 'input_schema' in fields or 'systemInstruction' in fields:return
     if isinstance(fields.get('name'),ast.Constant) and str(fields['name'].value).startswith('finish_'):return
   value=text(n,src)
   if human(value):chosen[(n.lineno,n.col_offset)]={'file':file.relative_to(root).as_posix(),'position':f'{n.lineno}:{n.col_offset+1}','role':role,'text':value}
  def leaves(n,role):
   if n is None:return
   if isinstance(n,(ast.Constant,ast.JoinedStr)):emit(n,role);return
   if isinstance(n,(ast.Subscript,ast.Attribute,ast.Compare)):return
   if isinstance(n,ast.Call):
    # The first .get argument is an internal key, only its default can be copy.
    if isinstance(n.func,ast.Attribute) and n.func.attr=='get':
     for arg in n.args[1:]:leaves(arg,role)
    return
   if isinstance(n,ast.Dict):
    for k,v in zip(n.keys,n.values):
     if isinstance(k,ast.Constant) and k.value in keys:leaves(v,role)
    return
   if isinstance(n,ast.IfExp):leaves(n.body,role);leaves(n.orelse,role);return
   for child in ast.iter_child_nodes(n):leaves(child,role)
  for n in ast.walk(tree):
   if isinstance(n,ast.Dict):
    # Messages sent to a provider and tool schemas are not UI copy.
    fields={k.value:v for k,v in zip(n.keys,n.values) if isinstance(k,ast.Constant)}
    if 'role' in fields or 'parameters' in fields or 'input_schema' in fields:continue
    if isinstance(fields.get('name'),ast.Constant) and str(fields['name'].value).startswith('finish_'):continue
    for k,v in zip(n.keys,n.values):
     if isinstance(k,ast.Constant) and k.value in keys:
      if file.name=='weekly.py' and k.value in {'text','description','name'}:continue
      leaves(v,'backend display field')
   if isinstance(n,ast.Call):
    name=n.func.id if isinstance(n.func,ast.Name) else n.func.attr if isinstance(n.func,ast.Attribute) else ''
    if name=='HTTPException':
     if len(n.args)>1:leaves(n.args[1],'API error')
     for kw in n.keywords:
      if kw.arg=='detail':leaves(kw.value,'API error')
    if name in {'ValueError','DemoBusy','WorldPreparationError'}:
     for arg in n.args:leaves(arg,'user-facing validation')
    for kw in n.keywords:
     if kw.arg in keys and name not in {'Field','ArgumentParser','add_argument'}:leaves(kw.value,'backend display argument')
   if isinstance(n,(ast.Assign,ast.AnnAssign)):
    targets=n.targets if isinstance(n,ast.Assign) else [n.target]
    for target in targets:
     if isinstance(target,ast.Name) and (re.search(r'(?i)(?:^|_)(?:labels?|title|message|description|explanation|notice|reason|question|move|name|headline|summary)$',target.id) or file.name=='narrator.py' and target.id in {'lead','body','split'}):
      if isinstance(n.value,ast.Dict):
       for val in n.value.values:leaves(val,'backend label map')
      else:leaves(n.value,'backend copy template')
   if file.name=='narrator.py' and isinstance(n,ast.Return) and n.value:leaves(n.value,'assistant fallback copy')
  rows.extend(chosen.values())
print(json.dumps(rows,ensure_ascii=False))
`;

async function get(endpoint) {
  const baseIndex=process.argv.indexOf('--base-url');
  const base=baseIndex>=0?process.argv[baseIndex+1]:'http://127.0.0.1:8008';
  const response=await fetch(`${base}/api${endpoint}`, {signal:AbortSignal.timeout(20000)});
  if(!response.ok)throw new Error(`${endpoint}: HTTP ${response.status}`);
  return response.json();
}
const runtimeKeys=new Set(['name','label','title','text','message','description','summary','reason','note','explanation','notice','display','magnitude','question','recommendation','interpretation','watch_next','headline','brand','format','district','supplier','error']);
function exportRuntime(endpoint,data,pointer='') {
  if(!data||typeof data!=='object')return;
  for(const [key,val] of Object.entries(data)) {
    const next=`${pointer}/${key.replaceAll('~','~0').replaceAll('/','~1')}`;
    if(key==='css'||key==='args'||key==='method'||key==='series'||key==='daily'||key==='intraday'||key==='per_sku'||key==='units'||key==='evidence'||key==='result')continue;
    if(key==='html'&&typeof val==='string'){exportHtml(`GET /api${endpoint}#${next}`,val,'Discover / current saved AI report');continue;}
    if(runtimeKeys.has(key)&&typeof val==='string'&&val.trim()&&!(key==='name'&&/\/(?:queries|tool_calls)\//.test(next)))add(`GET /api${endpoint}`,next,'current rendered record sample',val,'Current saved workspace data',next);
    if(val&&typeof val==='object')exportRuntime(endpoint,val,next);
  }
}
async function main() {
  function sourceFiles(directory){return fs.readdirSync(directory,{withFileTypes:true}).flatMap(entry=>entry.isDirectory()?sourceFiles(path.join(directory,entry.name)):/\.tsx?$/.test(entry.name)&&entry.name!=='types.ts'?[path.join(directory,entry.name)]:[])}
  const files=sourceFiles(path.join(root,'frontend/src')).sort();
  for(const file of files)exportTs(path.relative(root,file).replaceAll('\\','/'),fs.readFileSync(file,'utf8'));
  const tourFile=path.join(root,'frontend/public/tour-bundle.json');
  if(fs.existsSync(tourFile)){
    const tour=JSON.parse(fs.readFileSync(tourFile,'utf8'));
    for(const [id,answer] of [...Object.entries(tour.questions),...Object.entries(tour.branches).map(([id,branch])=>[id,branch.answer])])if(answer?.reply)add('frontend/public/tour-bundle.json',`answer/${id}`,'recorded Gemini reply sample',answer.reply.replace(/[ \t]+(\r?\n)/g,'$1'),'Guided tour / recorded assistant','recorded answer');
  }
  exportHtml('frontend/index.html',fs.readFileSync(path.join(root,'frontend/index.html'),'utf8'),'Browser tab');
  const demoCapture=path.join(root,'docs/screenshots/demo-overview/capture.json');
  if(fs.existsSync(demoCapture)) {
    const demo=JSON.parse(fs.readFileSync(demoCapture,'utf8'));
    for(const page of demo.pages) {
      add('scripts/build-demo-overview.cjs',`page-${page.index}/title`,'PDF title',page.title,'Demo overview PDF','capture');
      add('scripts/build-demo-overview.cjs',`page-${page.index}/caption`,'PDF caption',page.caption,'Demo overview PDF','capture');
    }
    add('scripts/render-demo-overview.py','page-1/footer','PDF footer','Synthetic demo data · Team T02 (Youth Storm)','Demo overview PDF','footer');
    add('scripts/render-demo-overview.py','page-number','PDF page number template','{index} / 5','Demo overview PDF','footer');
  }
  const pythonCandidates=[process.env.PYTHON,path.join(root,'.venv/Scripts/python.exe'),'python3','python'].filter(Boolean);
  let backend;const pythonErrors=[];
  for(const python of pythonCandidates){const p=spawnSync(python,['-c',pythonExtractor,root],{encoding:'utf8',maxBuffer:16*1024*1024,windowsHide:true,env:{...process.env,PYTHONIOENCODING:'utf-8'}});if(p.status===0){backend=JSON.parse(p.stdout);break;}pythonErrors.push(p.stderr||p.error?.message||String(p.status));}
  if(!backend)throw new Error('Python AST export failed: '+pythonErrors.join('\n'));
  for(const row of backend)add(row.file,row.position,row.role,row.text,'Backend-provided labels / validation / event feed',row.role);
  if(!process.argv.includes('--offline')){
    try {
      const boot=await get('/bootstrap');exportRuntime('/bootstrap',boot);
      const settings=await get('/demo-settings');exportRuntime('/demo-settings',settings);
      // All saved plan descriptions/reports are current real data; no generation.
      for(const plan of boot.plans||[]){
        const endpoint=`/plans/${encodeURIComponent(plan.id)}`;
        for(const suffix of ['', '/dashboard', '/simulation'])try{
          const data=await get(endpoint+suffix);exportRuntime(endpoint+suffix,data);
          if(suffix==='/simulation'&&data.result)exportRuntime(endpoint+suffix,data.result,'/result');
        }catch(error){console.error(`Runtime gap: ${error.message}`);}
      }
    } catch(error) {console.error(`Runtime gap: ${error.message}. Source inventory is still complete; rerun against the service to include saved text.`);}
  }
  const output=[...rows.entries()].sort(([a],[b])=>a.localeCompare(b,'en')).map(([,v])=>v);
  if(new Set(output.map(r=>r.id)).size!==output.length)throw new Error('Duplicate id');
  const columns=['id','screen','component/file','current text'];
  const quote=s=>'"'+String(s).replaceAll('"','""')+'"';
  const csv='\ufeff'+[columns,...output.map(r=>columns.map(c=>r[c]))].map(row=>row.map(quote).join(',')).join('\r\n')+'\r\n';
  fs.mkdirSync(path.join(root,'docs'),{recursive:true});fs.writeFileSync(path.join(root,'docs/ui-copy.csv'),csv,'utf8');
  console.log(JSON.stringify({rows:output.length,source:output.filter(r=>!r['component/file'].startsWith('GET ')).length,runtime:output.filter(r=>r['component/file'].startsWith('GET ')).length,output:'docs/ui-copy.csv',columns},null,2));
}
main().catch(error=>{console.error(error);process.exitCode=1;});
