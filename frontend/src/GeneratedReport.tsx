import { useEffect, useMemo, useRef, useState } from 'react';
import type { Detail, ReviewPresentation } from './types';
import { decorateReportProductIcons, nativeCohortMarkup } from './nativeReportCards';
import { evidenceSources } from './evidence';
import { interactionStyles, reportInteractionScript } from './reportInteractions';
import { fullDate } from './api';
import { reportCharts } from './reportCharts';

// Presentation content lives in an opaque-origin frame. Only this host bridge runs JS.
function isolatedDocument(presentation: ReviewPresentation, detail: Detail, channel: string) {
  const hostType = getComputedStyle(document.documentElement);
  const typeTokens = ['page','section','key','body','label'].map(role => `--type-${role}:${hostType.getPropertyValue(`--type-${role}`).trim()}`).join(';');
  const parsed = new DOMParser().parseFromString(presentation.html, 'text/html');
  parsed.querySelectorAll('script,iframe,frame,frameset,object,embed,applet,base,meta,link,form,input,textarea,select,svg').forEach(node => node.remove());
  parsed.querySelectorAll('*').forEach(node => {
    for (const attr of [...node.attributes]) {
      const name = attr.name.toLowerCase();
      if (name.startsWith('on') || ['nonce', 'src', 'srcset', 'srcdoc', 'action', 'formaction', 'target', 'ping'].includes(name) || ((name === 'href' || name.endsWith(':href')) && !attr.value.startsWith('#'))) node.removeAttribute(attr.name);
    }
    if (node instanceof HTMLElement) {
      node.style.removeProperty('font');
      node.style.removeProperty('font-size');
    }
  });
  parsed.querySelectorAll<HTMLElement>('figure[data-card="cohort"]').forEach(node=>{
    const card=detail.cohort_cards?.find(item=>item.id===node.dataset.id);
    if(card)node.innerHTML=nativeCohortMarkup(card);
    else node.remove();
  });
  decorateReportProductIcons(parsed,detail);
  const css = presentation.css.replace(/<\/style/gi, '<\\/style');
  const policy = `default-src 'none'; script-src 'nonce-${channel}'; style-src 'unsafe-inline'; img-src ${window.location.origin}/products/ data:; connect-src 'none'; font-src 'none'; media-src 'none'; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'`;
  const specs=[...parsed.querySelectorAll<HTMLElement>('figure[data-chart="line"]')].map(node=>({id:node.dataset.evidenceId||'',series:node.dataset.series||'actual,expected'}));
  const bridge = reportInteractionScript(detail, channel, reportCharts(detail,specs));
  return `<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="${policy}"><meta name="viewport" content="width=device-width, initial-scale=1"><style>:root{${typeTokens}}html{margin:0;background:#fff;color:#284f3d}body{margin:0;padding:4px 0 12px;font-family:system-ui,sans-serif;font-size:var(--type-body);line-height:1.8;display:flow-root;overflow-wrap:anywhere}*{box-sizing:border-box}svg,img{max-width:100%;height:auto}button,summary,[data-evidence-id]{cursor:pointer}button{font:inherit}details{margin:12px 0}summary{min-height:36px}:focus-visible{outline:2px solid #39744f;outline-offset:3px}@media(prefers-reduced-motion:reduce){*,*::before,*::after{animation:none!important;transition:none!important}}</style><style>${css}</style><style>${interactionStyles}</style></head><body>${parsed.body.innerHTML}<script nonce="${channel}">${bridge}</script></body></html>`;
}

export function GeneratedReport({presentation,detail,pending,onDiscuss,onSelectFinding,onDiscussEvidence,onOpenEvidence}:{presentation:ReviewPresentation;detail:Detail;pending:boolean;onDiscuss:(id:string)=>void;onSelectFinding?:(id:string)=>void;onDiscussEvidence?:(id:string)=>void;onOpenEvidence:(id:string)=>void}) {
  const frame = useRef<HTMLIFrameElement>(null);
  const [height, setHeight] = useState(480);
  const channel = useMemo(() => [...crypto.getRandomValues(new Uint8Array(24))].map(byte=>byte.toString(16).padStart(2,'0')).join(''), [presentation.title,presentation.html,presentation.css]);
  const document = useMemo(() => isolatedDocument(presentation, detail, channel), [presentation.title,presentation.html,presentation.css,detail,channel]);
  const queries = detail.review?.queries || [];
  const sources=evidenceSources(detail);
  useEffect(() => {setHeight(480)},[channel]);
  useEffect(() => {
    function receive(event:MessageEvent) {
      if (event.source!==frame.current?.contentWindow || !event.data || typeof event.data!=='object' || event.data.channel!==channel) return;
      const data=event.data;
      if (data.type==='resize' && typeof data.height==='number' && Number.isFinite(data.height) && data.height>0 && data.height<=30000) setHeight(Math.ceil(data.height));
      if (data.type==='discuss' && typeof data.id==='string') {
        const selected=detail.findings.find(f=>f.id===data.id);
        if(pending) return;
        if(selected){onSelectFinding?.(selected.id);onDiscuss(selected.id)}
        else if(queries.some((q,i)=>(q.id||`Q${i+1}`)===data.id)){if(onDiscussEvidence)onDiscussEvidence(data.id);else onDiscuss('')}
      }
      if (data.type==='evidence' && typeof data.id==='string' && sources.some(source=>source.id===data.id)) onOpenEvidence(data.id);
      if (data.type==='direction' && typeof data.id==='string' && detail.cohort_cards?.some(card=>card.id===data.id)) {
        window.dispatchEvent(new CustomEvent('scoop:focus-cohort',{detail:{id:data.id}}));
      }
    }
    window.addEventListener('message',receive);return()=>window.removeEventListener('message',receive);
  }, [channel, detail.findings, detail.cohort_cards, queries, pending, onDiscuss, onSelectFinding, onDiscussEvidence, onOpenEvidence]);
  return <article className="generated-report"><header className="generated-report-heading"><p>{detail.metadata?.facts_through?`Facts through ${fullDate(detail.metadata.facts_through)}`:fullDate(detail.plan.week_start)}</p><h2>{presentation.title}</h2></header>
    <iframe ref={frame} title={presentation.title || 'Weekly report'} className="generated-report-frame" sandbox="allow-scripts" referrerPolicy="no-referrer" srcDoc={document} style={{height}}/>
    <details className="report-evidence-index"><summary>Report evidence</summary><div>{sources.map(source=><button key={source.id} className="text-button" onClick={()=>onOpenEvidence(source.id)}>{source.title} · Open</button>)}</div>{detail.review?.created_at&&<small>Prepared {fullDate(detail.review.created_at)}</small>}</details>
  </article>;
}
