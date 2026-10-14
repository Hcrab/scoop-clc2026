import type { Detail } from './types';

export const interactionStyles = `
.sr-only{position:absolute!important;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
.chart svg{display:block;width:100%;height:auto}.chart svg text{font:var(--report-label-size,13px) system-ui,sans-serif;fill:#617566}
.chart .legend{display:flex;flex-wrap:wrap;gap:16px;font-size:var(--report-label-size,13px)}.chart .legend i{display:inline-block;width:16px;height:2px;margin-right:8px;vertical-align:middle}
.chart .chart-summary{font-size:var(--report-label-size,13px);color:#617566}.chart-empty{font-size:var(--report-body-size,15px);color:#617566}
figure[data-chart]{margin:16px 0}figure[data-chart] figcaption{font-weight:600;margin-bottom:8px}

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
export function reportInteractionScript(detail: Detail, channel: string, charts:ReturnType<typeof import('./reportCharts').reportCharts>) {
  const payload = JSON.stringify({channel, charts, queries: detail.review?.queries || [], findings: detail.findings})
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
 const chart=data.charts[id+'|actual,expected,prior'];
 if(chart) mountChart(panel,chart);else panel.append(element('p','No daily series in this evidence.'));
 const close=button('Collapse trend',()=>{toggle(false);trigger.focus()});panel.append(close);const summary=card.querySelector('[data-report-summary]');if(summary)summary.after(panel);else card.append(panel);toggle(true);
}
function mountChart(panel,chart){
 let range=chart.defaultRange;const controls=element('div',undefined,'report-range'),plot=element('div');
 const draw=()=>{plot.innerHTML=chart.html[range];controls.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.range===range)));schedule()};
 [...chart.ranges.map(String),'all'].forEach(value=>{const b=button(value==='all'?'All available':value+' days',()=>{range=value;draw()});b.dataset.range=value;controls.append(b)});
 panel.append(controls,plot);draw();
}
const seriesKey=value=>['actual','expected','prior'].filter(key=>value.split(',').map(s=>s.trim()).includes(key)).join(',');
document.querySelectorAll('figure[data-chart="line"]').forEach(figure=>{
 const id=figure.dataset.evidenceId,chart=data.charts[id+'|'+seriesKey(figure.dataset.series||'actual,expected')],caption=figure.querySelector('figcaption');
 figure.replaceChildren();if(caption)figure.append(caption);
 if(chart)mountChart(figure,chart);else figure.append(element('p','No daily series in this evidence.'));
});
document.querySelectorAll('[data-evidence-id],[data-trend-id]').forEach(el=>{if(el.tagName==='FIGURE')return;if(!el.hasAttribute('tabindex'))el.tabIndex=0;if(el.tagName!=='BUTTON'&&!el.hasAttribute('role'))el.setAttribute('role','button');el.setAttribute('aria-expanded','false');if(!el.hasAttribute('aria-label'))el.setAttribute('aria-label',(el.hasAttribute('data-trend-id')?'Expand trend ':'View evidence ')+(el.dataset.trendId||el.dataset.evidenceId))});
const activate=event=>{if(event.target instanceof Element&&event.target.closest('.report-inline,figure[data-chart]'))return;const el=event.target instanceof Element?event.target.closest('[data-trend-id],[data-evidence-id]'):null;if(!el||el.tagName==='FIGURE')return;event.preventDefault();if(el.hasAttribute('data-trend-id'))trend(el,el.dataset.trendId);else evidence(el,el.dataset.evidenceId)};
document.addEventListener('click',activate);document.addEventListener('keydown',event=>{if((event.key==='Enter'||event.key===' ')&&event.target?.tagName!=='BUTTON')activate(event)});
new ResizeObserver(schedule).observe(document.body);document.addEventListener('toggle',schedule,true);window.addEventListener('load',schedule);schedule();
})()`;
}
