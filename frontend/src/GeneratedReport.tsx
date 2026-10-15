import { useEffect, useMemo, useRef, useState } from 'react';
import type { Detail, ReviewPresentation } from './types';
import { Chart, DataView, Icon } from './ui';
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
  const css = presentation.css.replace(/<\/style/gi, '<\\/style');
  const policy = `default-src 'none'; script-src 'nonce-${channel}'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; font-src 'none'; media-src 'none'; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'`;
  const specs=[...parsed.querySelectorAll<HTMLElement>('figure[data-chart="line"]')].map(node=>({id:node.dataset.evidenceId||'',series:node.dataset.series||'actual,expected'}));
  const bridge = reportInteractionScript(detail, channel, reportCharts(detail,specs));
  return `<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="${policy}"><meta name="viewport" content="width=device-width, initial-scale=1"><style>:root{${typeTokens}}html{margin:0;background:#fff;color:#284f3d}body{margin:0;padding:4px 0 12px;font-family:system-ui,sans-serif;font-size:var(--type-body);line-height:1.8;display:flow-root;overflow-wrap:anywhere}*{box-sizing:border-box}svg,img{max-width:100%;height:auto}button,summary,[data-evidence-id]{cursor:pointer}button{font:inherit}details{margin:12px 0}summary{min-height:36px}:focus-visible{outline:2px solid #39744f;outline-offset:3px}@media(prefers-reduced-motion:reduce){*,*::before,*::after{animation:none!important;transition:none!important}}</style><style>${css}</style><style>${interactionStyles}</style></head><body>${parsed.body.innerHTML}<script nonce="${channel}">${bridge}</script></body></html>`;
}

export function GeneratedReport({presentation,detail,pending,onDiscuss,onSelectFinding,onDiscussEvidence}:{presentation:ReviewPresentation;detail:Detail;pending:boolean;onDiscuss:(id:string)=>void;onSelectFinding?:(id:string)=>void;onDiscussEvidence?:(id:string)=>void}) {
  const frame = useRef<HTMLIFrameElement>(null);
  const [height, setHeight] = useState(480), [evidenceId, setEvidenceId] = useState('');
  const channel = useMemo(() => [...crypto.getRandomValues(new Uint8Array(24))].map(byte=>byte.toString(16).padStart(2,'0')).join(''), [presentation.title,presentation.html,presentation.css]);
  const document = useMemo(() => isolatedDocument(presentation, detail, channel), [presentation.title,presentation.html,presentation.css,detail,channel]);
  const queries = detail.review?.queries || [];
  const query = queries.find((q,i)=>(q.id || `Q${i+1}`)===evidenceId);
  const finding = detail.findings.find(f=>f.id===evidenceId);
  const findingTitle = finding ? (typeof finding.evidence.display==='string'?finding.evidence.display:finding.tag_id) : '';
  useEffect(() => {setHeight(480);setEvidenceId('')},[channel]);
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
      if (data.type==='evidence' && typeof data.id==='string' && (detail.findings.some(f=>f.id===data.id)||queries.some((q,i)=>(q.id||`Q${i+1}`)===data.id))) setEvidenceId(data.id);
    }
    window.addEventListener('message',receive);return()=>window.removeEventListener('message',receive);
  }, [channel, detail.findings, queries, pending, onDiscuss, onSelectFinding, onDiscussEvidence]);
  return <article className="generated-report"><header className="generated-report-heading"><p>{detail.metadata?.facts_through?`Facts through ${fullDate(detail.metadata.facts_through)}`:fullDate(detail.plan.week_start)}</p><h2>{presentation.title}</h2></header>
    <iframe ref={frame} title={presentation.title || 'Weekly report'} className="generated-report-frame" sandbox="allow-scripts" referrerPolicy="no-referrer" srcDoc={document} style={{height}}/>
    <details className="report-evidence-index"><summary>Report evidence</summary><div>{queries.map((q,i)=><button key={q.id||i} className="text-button" onClick={()=>setEvidenceId(q.id||`Q${i+1}`)}>{q.id||`Q${i+1}`} · {q.name.replaceAll('_',' ')}</button>)}{detail.findings.map(f=><button key={f.id} className="text-button" onClick={()=>setEvidenceId(f.id)}>{typeof f.evidence.display==='string'?f.evidence.display:f.tag_id} · {f.district}</button>)}</div>{detail.review?.created_at&&<small>Prepared {fullDate(detail.review.created_at)}</small>}</details>
    {evidenceId&&(query||finding)&&<section className="report-host-evidence" aria-label={finding?findingTitle:`Evidence ${evidenceId}`}><h3>{finding?findingTitle:`Evidence ${evidenceId}`}</h3>
      {finding?<><p className="muted">{finding.district}</p><Chart data={finding.series} percent lines={[{key:'actual_share',label:'Actual share of demand',color:'#205a4e'},{key:'expected_share',label:'Expected for the weather',color:'#a695bf',dashed:true}]}/><p className="evidence-explanation">{finding.explanation}</p><details className="review-exploration"><summary>Checks and supporting evidence</summary><DataView value={finding.evidence.checks}/><DataView value={finding.hypotheses}/></details></>:<><p className="muted">{query!.name.replaceAll('_',' ')}</p><DataView value={query!.args}/><details className="review-exploration"><summary>Full saved result</summary><DataView value={query!.result}/></details></>}
      <div className="modal-actions"><button className="button ghost" onClick={()=>setEvidenceId('')}>Close</button><button className="button primary" disabled={pending} onClick={()=>{if(finding){onSelectFinding?.(finding.id);onDiscuss(finding.id)}else if(onDiscussEvidence)onDiscussEvidence(evidenceId);else onDiscuss('');setEvidenceId('')}}><Icon name="spark" size={16}/>Discuss this evidence</button></div>
    </section>}
  </article>;
}
