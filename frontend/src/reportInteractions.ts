import type { Detail } from './types';
import { evidenceSources } from './evidence';

export const interactionStyles = `
.sr-only{position:absolute!important;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
.chart svg{display:block;width:100%;height:auto}.chart svg text{font-family:system-ui,sans-serif;font-size:var(--type-label)!important;fill:#617566}
.chart .legend{display:flex;flex-wrap:wrap;gap:16px;font-size:var(--type-label)}.chart .legend i{display:inline-block;width:16px;height:2px;margin-right:8px;vertical-align:middle}
.chart .chart-summary{font-size:var(--type-label);color:#617566}.chart-empty{font-size:var(--type-body);color:#617566}
figure[data-chart]{margin:16px 0;height:auto!important;max-height:none!important;min-height:0}figure[data-chart] figcaption{font-weight:600;margin-bottom:8px}
figure[data-card="cohort"]{margin:16px 0!important}
.report-range button{border:1px solid #dde5d8;border-radius:7px;background:white;color:#476b56;padding:5px 11px;font-size:var(--type-label);min-height:32px}.report-range button[aria-pressed=true]{background:#e5eee3;color:#254f3e}

[data-trend-id],[data-evidence-id]{cursor:pointer;text-decoration:none}
.report-card-expanded{grid-column:1/-1!important;flex-basis:100%!important;width:100%!important;max-width:none!important}
.report-card-expanded [data-report-summary]{display:none!important}
.report-inline{grid-column:1/-1;margin:20px 0 8px;padding:18px;background:#f6f8f3;border:1px solid #e0e7dc;border-radius:10px;color:#284f3d;font-family:system-ui,sans-serif;line-height:1.7;clear:both;min-width:0}
.report-inline[hidden]{display:none!important}
.report-inline h4{margin:0;font-size:var(--type-section)}.report-inline-head{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:12px}
.report-inline button{border:1px solid #dde5d8;border-radius:7px;background:white;color:#476b56;padding:5px 11px;font-size:var(--type-label);min-height:32px}.report-inline button:disabled{opacity:.45;cursor:default}.report-inline button[aria-pressed=true]{background:#e5eee3;color:#254f3e}
.report-range{display:flex;gap:4px;flex-wrap:wrap}.report-legend{display:flex;gap:18px;flex-wrap:wrap;font-size:var(--type-label);color:#617566}.report-legend span:before{content:'';display:inline-block;width:18px;border-top:2px solid #377663;vertical-align:middle;margin-right:6px}.report-legend span:nth-child(2):before{border-color:#9985b6;border-top-style:dashed}.report-legend span:nth-child(3):before{border-color:#91a7b3;border-top-style:dotted}
.report-plot{display:block;width:100%;height:auto;margin-top:12px}.report-inline pre{white-space:pre-wrap;overflow-wrap:anywhere;font-family:Consolas,monospace;font-size:var(--type-label);line-height:1.7;margin:8px 0}.report-inline dl{display:grid;grid-template-columns:minmax(90px,auto) 1fr;gap:4px 16px;margin:10px 0}.report-inline dt{color:#718273}.report-inline dd{margin:0}.report-inline p{margin:8px 0}.report-inline details{margin:10px 0}.report-inline-actions{display:flex;gap:8px;justify-content:flex-end;margin-top:14px}
.native-cohort-card{display:flex;gap:16px;padding:18px;background:#f6f8f3;border:1px solid #dce6dc;border-radius:12px;color:#284f3d;position:relative}.native-cohort-icon{display:grid;place-items:center;width:42px;height:42px;flex:none;border-radius:50%;background:#dfede2;color:#205a4e;font-size:var(--type-section)!important;font-weight:700}.native-cohort-main{min-width:0;flex:1}.native-cohort-main h4,.native-cohort-main p{margin:0}.native-cohort-effect,.native-cohort-impact{color:#607563}.native-cohort-cases{display:block;margin:9px 0 2px;font-size:var(--type-key)!important;line-height:1.15;font-variant-numeric:tabular-nums}.native-cohort-main button{margin-top:10px;padding:5px 0;background:none;border:0;color:#205a4e;text-decoration:underline;cursor:pointer}.native-cohort-card>.product-icon{align-self:flex-start}@media(max-width:520px){.native-cohort-card>.product-icon{width:48px!important;height:48px!important}}
.product-icon{position:relative;display:inline-block;flex:none;overflow:hidden;border-radius:16%;vertical-align:middle;background:#f7f4e9}.product-icon-fallback,.product-icon img{position:absolute;inset:0;display:block;width:100%;height:100%;object-fit:cover}.product-icon img{color:transparent}
.report-evidence-summary{color:#607563;margin-right:8px;font-size:var(--type-label)!important}
body *{font-size:var(--type-body)!important}
body h1{font-size:var(--type-page)!important}body h2,body h3,body h4{font-size:var(--type-section)!important}
body small,body figcaption,body .metric-label,body .card-meta,body .chart .legend,body .chart svg text,body .report-range button{font-size:var(--type-label)!important}
body [data-report-card] .metric-val{font-size:var(--type-body)!important}
body [data-report-card] .metric-val:first-child{font-size:var(--type-key)!important}
body [data-report-card] .metric-item:first-child .metric-val{font-size:var(--type-key)!important}
body .card-meta,body .metric-label{text-transform:none!important;letter-spacing:normal!important}
`;

// This is host-owned code, never generated JavaScript. Escape every script terminator in data.
export function reportInteractionScript(detail: Detail, channel: string, charts:ReturnType<typeof import('./reportCharts').reportCharts>) {
  const payload = JSON.stringify({channel, charts, queries: evidenceSources(detail).filter(source=>source.kind==='query').map(source=>({id:source.id,title:source.title,summary:source.summary})), findings: detail.findings.map(f=>({id:f.id,tag_id:f.tag_id,evidence:{display:f.evidence.display}}))})
    .replace(/</g, '\\u003c').replace(/>/g, '\\u003e').replace(/&/g, '\\u0026').replace(/\u2028/g, '\\u2028').replace(/\u2029/g, '\\u2029');
  return String.raw`(()=>{
const data=${payload},send=value=>parent.postMessage({channel:data.channel,...value},'*');
document.querySelectorAll('.product-icon img').forEach(img=>{const failed=()=>{img.hidden=true;img.style.display='none'};img.addEventListener('error',failed);if(img.complete&&img.naturalWidth===0)failed()});
let scheduled=false,lastHeight=0,serial=0;
const schedule=()=>{if(scheduled)return;scheduled=true;requestAnimationFrame(()=>{scheduled=false;const height=Math.ceil(document.body.getBoundingClientRect().height);if(height!==lastHeight){lastHeight=height;send({type:'resize',height})}})};
const element=(tag,text,className)=>{const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(className)el.className=className;return el};
// Inline priority wins over authored selector rules while leaving layout, color,
// table sizing, and every piece of authored copy untouched.
const keyElements=new Set(Array.from(document.querySelectorAll('[data-report-card]')).map(card=>card.querySelector('[data-report-key],.native-cohort-cases,.metric-val,.key-number,.key-metric,.stat-value,.big-number')).filter(Boolean));
document.body.querySelectorAll('*').forEach(el=>{
 if(!(el instanceof HTMLElement))return;
 const role=keyElements.has(el)?'key':/^H1$/.test(el.tagName)?'page':/^H[234]$/.test(el.tagName)?'section':el.matches('small,figcaption,button,.metric-label,.card-meta,.native-cohort-impact,.native-cohort-effect,.report-evidence-summary')?'label':'body';
 el.style.setProperty('font-size','var(--type-'+role+')','important');
});
const entries=new Map(data.queries.map((q,i)=>[q.id||'Q'+(i+1),{...q,kind:'query'}]));data.findings.forEach(f=>entries.set(f.id,{...f,kind:'finding'}));
const pretty=value=>JSON.stringify(value,null,2),label=key=>key.replaceAll('_',' ');
const cardFor=el=>el.closest('[data-report-card],article,.card')||el.parentElement;
const button=(text,run)=>{const el=element('button',text);el.type='button';el.addEventListener('click',run);return el};
const titleFor=item=>item.kind==='query'?item.title:(typeof item.evidence.display==='string'?item.evidence.display:item.tag_id);
const setOpen=(trigger,open,panel)=>{trigger.setAttribute('aria-expanded',String(open));trigger.setAttribute('aria-controls',panel.id)};
function evidence(_trigger,id){if(entries.has(id))send({type:'evidence',id})}
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
 let range=chart.defaultRange,lastWidth='';const controls=element('div',undefined,'report-range'),plot=element('div');
 const widths=[240,320,480,680];
 const draw=()=>{
  const available=panel.clientWidth||panel.parentElement?.clientWidth||320;
  const width=String(widths.filter(candidate=>candidate<=available).at(-1)||widths[0]);
  if(width!==lastWidth||plot.dataset.range!==range){plot.innerHTML=chart.html[range][width];lastWidth=width;plot.dataset.range=range}
  controls.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.range===range)));schedule()
 };
 [...chart.ranges.map(String),'all'].forEach(value=>{const b=button(value==='all'?'All available':value+' days',()=>{range=value;draw()});b.dataset.range=value;controls.append(b)});
 panel.append(controls,plot);new ResizeObserver(draw).observe(panel);draw();
}
const seriesKey=value=>['actual','expected','prior'].filter(key=>value.split(',').map(s=>s.trim()).includes(key)).join(',');
document.querySelectorAll('figure[data-chart="line"]').forEach(figure=>{
 const id=figure.dataset.evidenceId,chart=data.charts[id+'|'+seriesKey(figure.dataset.series||'actual,expected')],caption=figure.querySelector('figcaption');
 figure.replaceChildren();if(caption)figure.append(caption);
 if(chart)mountChart(figure,chart);else figure.append(element('p','No daily series in this evidence.'));
});
document.querySelectorAll('[data-evidence-id],[data-trend-id]').forEach(el=>{if(el.tagName==='FIGURE')return;if(!el.hasAttribute('tabindex'))el.tabIndex=0;if(el.tagName!=='BUTTON'&&!el.hasAttribute('role'))el.setAttribute('role','button');if(el.hasAttribute('data-trend-id'))el.setAttribute('aria-expanded','false');if(!el.hasAttribute('aria-label'))el.setAttribute('aria-label',(el.hasAttribute('data-trend-id')?'Expand trend for ':'Open evidence: ')+(entries.get(el.dataset.trendId||el.dataset.evidenceId)?titleFor(entries.get(el.dataset.trendId||el.dataset.evidenceId)):(el.dataset.trendId||el.dataset.evidenceId)));if(el.hasAttribute('data-evidence-id')&&el.tagName==='BUTTON'&&!el.closest('.native-cohort-card')){const item=entries.get(el.dataset.evidenceId);if(item){const summary=element('span',item.kind==='finding'?titleFor(item):item.summary);summary.className='report-evidence-summary';el.before(summary);el.textContent='Open'}}});
const activate=event=>{if(event.target instanceof Element&&event.target.closest('.report-inline,figure[data-chart]'))return;const el=event.target instanceof Element?event.target.closest('[data-trend-id],[data-evidence-id]'):null;if(!el||el.tagName==='FIGURE')return;event.preventDefault();if(el.hasAttribute('data-trend-id'))trend(el,el.dataset.trendId);else evidence(el,el.dataset.evidenceId)};
document.addEventListener('click',activate);document.addEventListener('keydown',event=>{if((event.key==='Enter'||event.key===' ')&&event.target?.tagName!=='BUTTON')activate(event)});
new ResizeObserver(schedule).observe(document.body);document.addEventListener('toggle',schedule,true);window.addEventListener('load',schedule);schedule();
})()`;
}
