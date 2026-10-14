import type { Detail } from './types';

export const interactionStyles = `
[data-trend-id],[data-evidence-id]{cursor:pointer;text-decoration:none}
.report-card-expanded{grid-column:1/-1!important;flex-basis:100%!important;width:100%!important;max-width:none!important}
.report-card-expanded [data-report-summary]{display:none!important}
.report-inline{grid-column:1/-1;margin:20px 0 8px;padding:18px;background:#f6f8f3;border:1px solid #e0e7dc;border-radius:10px;color:#284f3d;font:13px/1.7 system-ui,sans-serif;clear:both;min-width:0}
.report-inline[hidden]{display:none!important}
.report-inline h4{margin:0;font-size:13px}.report-inline-head{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:12px}
.report-inline button{border:1px solid #dde5d8;border-radius:7px;background:white;color:#476b56;padding:5px 11px;font-size:12px;min-height:32px}.report-inline button:disabled{opacity:.45;cursor:default}.report-inline button[aria-pressed=true]{background:#e5eee3;color:#254f3e}
.report-range{display:flex;gap:4px;flex-wrap:wrap}.report-legend{display:flex;gap:18px;flex-wrap:wrap;font-size:12px;color:#617566}.report-legend span:before{content:'';display:inline-block;width:18px;border-top:2px solid #377663;vertical-align:middle;margin-right:6px}.report-legend span:nth-child(2):before{border-color:#9985b6;border-top-style:dashed}.report-legend span:nth-child(3):before{border-color:#91a7b3;border-top-style:dotted}
.report-plot{display:block;width:100%;height:auto;margin-top:12px}.report-inline pre{white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.7 Consolas,monospace;margin:8px 0}.report-inline dl{display:grid;grid-template-columns:minmax(90px,auto) 1fr;gap:4px 16px;margin:10px 0}.report-inline dt{color:#718273}.report-inline dd{margin:0}.report-inline p{margin:8px 0}.report-inline details{margin:10px 0}.report-inline-actions{display:flex;gap:8px;justify-content:flex-end;margin-top:14px}
`;

// This is host-owned code, never generated JavaScript. Escape every script terminator in data.
export function reportInteractionScript(detail: Detail, channel: string) {
  const payload = JSON.stringify({channel, queries: detail.review?.queries || [], findings: detail.findings})
    .replace(/</g, '\\u003c').replace(/>/g, '\\u003e').replace(/&/g, '\\u0026').replace(/\u2028/g, '\\u2028').replace(/\u2029/g, '\\u2029');
  return String.raw`(()=>{
const data=${payload},send=value=>parent.postMessage({channel:data.channel,...value},'*');
let scheduled=false,lastHeight=0,serial=0;
const schedule=()=>{if(scheduled)return;scheduled=true;requestAnimationFrame(()=>{scheduled=false;const height=Math.ceil(document.body.getBoundingClientRect().height);if(height!==lastHeight){lastHeight=height;send({type:'resize',height})}})};
const element=(tag,text,className)=>{const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(className)el.className=className;return el};
const entries=new Map(data.queries.map((q,i)=>[q.id||'Q'+(i+1),{...q,kind:'query'}]));data.findings.forEach(f=>entries.set(f.id,{...f,kind:'finding'}));
const pretty=value=>JSON.stringify(value,null,2),label=key=>key.replaceAll('_',' ');
const cardFor=el=>el.closest('[data-report-card],article,.card')||el.parentElement;
const button=(text,run)=>{const el=element('button',text);el.type='button';el.addEventListener('click',run);return el};
const titleFor=item=>item.kind==='query'?label(item.name):(typeof item.evidence.display==='string'?item.evidence.display:item.tag_id);
const setOpen=(trigger,open,panel)=>{trigger.setAttribute('aria-expanded',String(open));trigger.setAttribute('aria-controls',panel.id)};
function evidence(trigger,id){
 const item=entries.get(id);if(!item)return;const card=cardFor(trigger);let panel=Array.from(card.children).find(n=>n.dataset.reportEvidence===id);
 if(panel){const open=panel.hidden;panel.hidden=!open;setOpen(trigger,open,panel);schedule();return}
 panel=element('div',undefined,'report-inline');panel.dataset.reportEvidence=id;panel.id='report-evidence-'+(++serial);panel.setAttribute('role','region');panel.setAttribute('aria-label','Evidence '+id);
 const head=element('div',undefined,'report-inline-head');head.append(element('h4',id+' · '+titleFor(item)));panel.append(head);
 if(item.kind==='query'){
  panel.append(element('h4','Scope examined'),element('pre',pretty(item.args)));
  const result=item.result;const summary=element('dl');if(result&&typeof result==='object')Object.entries(result).forEach(([key,value])=>{
   let text;if(Array.isArray(value))text=value.length+' rows';else if(value!==null&&typeof value==='object')text=Object.entries(value).filter(([,v])=>v===null||typeof v!=='object').map(([k,v])=>label(k)+': '+String(v)).slice(0,8).join(' · ');else text=String(value);
   if(text){summary.append(element('dt',label(key)),element('dd',text))}
  });else summary.append(element('dd',String(result)));panel.append(summary);
  const raw=element('details');raw.append(element('summary','Full saved result'),element('pre',pretty(result)));panel.append(raw);
 }else{
  panel.append(element('p',item.district),element('p',item.explanation));const checks=element('details');checks.append(element('summary','Checks and supporting evidence'),element('pre',pretty({checks:item.evidence.checks,hypotheses:item.hypotheses})));panel.append(checks);
 }
 const actions=element('div',undefined,'report-inline-actions');actions.append(button('Close',()=>{panel.hidden=true;setOpen(trigger,false,panel);trigger.focus();schedule()}),button('Discuss this evidence',()=>send({type:'discuss',id})));panel.append(actions);card.append(panel);setOpen(trigger,true,panel);schedule();
}
function trend(trigger,id){
 const item=entries.get(id);if(!item)return;const card=cardFor(trigger);let panel=Array.from(card.children).find(n=>n.dataset.reportTrend===id);
 const toggle=open=>{panel.hidden=!open;card.classList.toggle('report-card-expanded',open);setOpen(trigger,open,panel);trigger.setAttribute('aria-label',(open?'Collapse':'Expand')+' '+titleFor(item)+' trend');schedule()};
 if(panel){toggle(panel.hidden);return}
 panel=element('div',undefined,'report-inline');panel.dataset.reportTrend=id;panel.id='report-trend-'+(++serial);panel.setAttribute('role','region');panel.setAttribute('aria-label',titleFor(item)+' daily trend');
 const raw=item.kind==='query'?item.result?.daily:item.series;
 const rows=Array.isArray(raw)?raw.filter(r=>r&&typeof r.date==='string'&&Number.isFinite(Date.parse(r.date))).map(r=>({date:r.date,actual:item.kind==='finding'?r.actual_share:r.requested_units,expected:item.kind==='finding'?r.expected_share:r.expected_units,prior:r.prior_year_requested_units??r.prior_year_units??r.last_year_requested_units})).sort((a,b)=>a.date.localeCompare(b.date)):[];
 const unique=Array.from(new Map(rows.map(r=>[r.date,r])).values());
 const available=days=>{const tail=unique.slice(-days);return tail.length===days&&tail.every((r,i)=>!i||Date.parse(r.date)-Date.parse(tail[i-1].date)===86400000)};
 let days=available(14)?14:available(7)?7:unique.length;
 const head=element('div',undefined,'report-inline-head'),legend=element('div',undefined,'report-legend'),ranges=element('div',undefined,'report-range');ranges.setAttribute('role','group');ranges.setAttribute('aria-label','Trend time range');legend.append(element('span','Actual'),element('span','Expected'));head.append(legend,ranges);panel.append(head);
 const plot=document.createElementNS('http://www.w3.org/2000/svg','svg');plot.setAttribute('viewBox','0 0 900 280');plot.setAttribute('role','img');plot.setAttribute('aria-label','Daily actual and expected '+(item.kind==='finding'?'share of demand':'requested units'));plot.classList.add('report-plot');panel.append(plot);
 const note=element('p');note.setAttribute('role','status');panel.append(note);
 const svg=(tag,attrs,text)=>{const n=document.createElementNS('http://www.w3.org/2000/svg',tag);Object.entries(attrs).forEach(([k,v])=>n.setAttribute(k,String(v)));if(text!==undefined)n.textContent=text;return n};
 const format=v=>item.kind==='finding'?(v*100).toFixed(1)+'%':Math.round(v).toLocaleString();
 function draw(){
  plot.replaceChildren();const shown=unique.slice(-days),prior=shown.some(r=>Number.isFinite(r.prior));legend.querySelectorAll('span:nth-child(3)').forEach(n=>n.remove());if(prior)legend.append(element('span','Prior year'));
  const values=shown.flatMap(r=>[r.actual,r.expected,r.prior]).filter(Number.isFinite);if(!values.length){note.textContent='No saved daily series for this query.';plot.hidden=true;return}plot.hidden=false;
  const low=Math.min(0,...values),max=Math.max(...values),high=max===low?low+1:max*1.08,x=i=>60+i*815/Math.max(1,shown.length-1),y=v=>22+(high-v)*215/(high-low);
  for(let i=0;i<5;i++){const value=low+(high-low)*i/4;plot.append(svg('line',{x1:60,x2:875,y1:y(value),y2:y(value),stroke:'#e2e8df'}),svg('text',{x:50,y:y(value)+4,'text-anchor':'end',fill:'#718273','font-size':11},format(value)))}
  [0,Math.floor((shown.length-1)/2),shown.length-1].filter((v,i,a)=>a.indexOf(v)===i).forEach(i=>plot.append(svg('text',{x:x(i),y:267,'text-anchor':'middle',fill:'#718273','font-size':11},shown[i].date.slice(5))));
  [['expected','#9985b6','7 5'],['prior','#91a7b3','2 5'],['actual','#377663','']].forEach(([key,color,dash])=>{let segment=[];const flush=()=>{if(segment.length)plot.append(svg('polyline',{points:segment.join(' '),fill:'none',stroke:color,'stroke-width':2.5,'stroke-dasharray':dash,'stroke-linejoin':'round'}));segment=[]};shown.forEach((r,i)=>{if(Number.isFinite(r[key]))segment.push(x(i)+','+y(r[key]));else flush()});flush()});
  shown.forEach((r,i)=>{if(!Number.isFinite(r.actual))return;const point=svg('circle',{cx:x(i),cy:y(r.actual),r:5,fill:'#377663',tabindex:0});const text=r.date+' · Actual '+format(r.actual)+' · Expected '+(Number.isFinite(r.expected)?format(r.expected):'missing')+(Number.isFinite(r.prior)?' · Prior year '+format(r.prior):'');point.setAttribute('aria-label',text);point.append(svg('title',{},text));plot.append(point)});
  note.textContent=shown[0].date+' – '+shown[shown.length-1].date+' · '+(item.kind==='finding'?'Share of demand':'Daily requested units')+(prior?'':' · Prior-year series not saved.');
  ranges.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(Number(b.dataset.days)===days)));schedule();
 }
 [7,14,28].forEach(n=>{const b=button(n+' days',()=>{days=n;draw()});b.dataset.days=String(n);b.disabled=!available(n);if(b.disabled)b.title='This range is not in the saved daily data';ranges.append(b)});
 const close=button('Collapse trend',()=>{toggle(false);trigger.focus()});panel.append(close);const summary=card.querySelector('[data-report-summary]');if(summary)summary.after(panel);else card.append(panel);toggle(true);draw();
}
document.querySelectorAll('[data-evidence-id],[data-trend-id]').forEach(el=>{if(!el.hasAttribute('tabindex'))el.tabIndex=0;if(el.tagName!=='BUTTON'&&!el.hasAttribute('role'))el.setAttribute('role','button');el.setAttribute('aria-expanded','false');if(!el.hasAttribute('aria-label'))el.setAttribute('aria-label',(el.hasAttribute('data-trend-id')?'Expand trend ':'View evidence ')+(el.dataset.trendId||el.dataset.evidenceId))});
const activate=event=>{if(event.target instanceof Element&&event.target.closest('.report-inline'))return;const el=event.target instanceof Element?event.target.closest('[data-trend-id],[data-evidence-id]'):null;if(!el)return;event.preventDefault();if(el.hasAttribute('data-trend-id'))trend(el,el.dataset.trendId);else evidence(el,el.dataset.evidenceId)};
document.addEventListener('click',activate);document.addEventListener('keydown',event=>{if((event.key==='Enter'||event.key===' ')&&event.target?.tagName!=='BUTTON')activate(event)});
new ResizeObserver(schedule).observe(document.body);document.addEventListener('toggle',schedule,true);window.addEventListener('load',schedule);schedule();
})()`;
}
