import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Chart, DataView } from './ui';
import { evidenceSections, evidenceUrl, type EvidenceSource } from './evidence';
import { CohortDrilldown } from './CohortDrilldown';
import type { CohortDrilldownData } from './types';
import './evidence.css';

function cell(value:unknown):string{if(value==null)return '—';if(typeof value==='number')return value.toLocaleString('en-HK',{maximumFractionDigits:3});if(typeof value==='string'||typeof value==='boolean')return String(value);if(Array.isArray(value))return value.length>5?`${value.length} items`:value.map(cell).join(', ');return Object.entries(value).filter(([,v])=>v==null||typeof v!=='object').slice(0,5).map(([k,v])=>`${label(k)}: ${cell(v)}`).join(' · ')||'Details'}
const label=(value:string)=>value.replaceAll('_',' ').replace(/\b\w/g,match=>match.toUpperCase());
export function EvidenceModal({source,planId,onClose}:{source:EvidenceSource;planId:string;onClose:()=>void}){
 const dialog=useRef<HTMLElement>(null);
 const sections=useMemo(()=>evidenceSections(source.result),[source.result]);
 const savedResult=useMemo(()=>JSON.stringify(source.result,null,2),[source.result]);
 const drilldown=source.id.startsWith('Q-cohort-')&&source.result&&typeof source.result==='object'?'drilldown' in source.result?(source.result as {drilldown?:CohortDrilldownData}).drilldown:undefined:undefined;
 const [section,setSection]=useState(0),[search,setSearch]=useState(''),[sort,setSort]=useState(''),[descending,setDescending]=useState(false),[page,setPage]=useState(0);
 useEffect(()=>{setSection(0);setSearch('');setSort('');setPage(0)},[source.id]);
 useLayoutEffect(()=>{
   const before=document.activeElement as HTMLElement|null,overflow=document.body.style.overflow;
   document.body.style.overflow='hidden';dialog.current?.focus();
   const keys=(event:KeyboardEvent)=>{
     if(event.key==='Escape')onClose();
     if(event.key==='Tab'){
       const items=Array.from(dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled),input,select,a[href],summary')||[]),first=items[0],last=items.at(-1);
       if(event.shiftKey&&(document.activeElement===first||document.activeElement===dialog.current)){event.preventDefault();last?.focus()}
       else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus()}
     }
   };
   window.addEventListener('keydown',keys);
   return()=>{window.removeEventListener('keydown',keys);document.body.style.overflow=overflow;before?.focus({preventScroll:true})};
 },[onClose]);
 const current=sections[section],columns=Array.from(new Set((current?.rows||[]).flatMap(row=>Object.keys(row))));
 const rows=(current?.rows||[]).filter(row=>!search||(JSON.stringify(row)+' '+Object.values(row).map(cell).join(' ')).toLowerCase().includes(search.toLowerCase())).sort((a,b)=>sort?(descending?-1:1)*(typeof a[sort]==='number'&&typeof b[sort]==='number'?(a[sort] as number)-(b[sort] as number):cell(a[sort]).localeCompare(cell(b[sort]),undefined,{numeric:true})):0);
 const pages=Math.max(1,Math.ceil(rows.length/25));
 return <div className="evidence-backdrop" role="presentation" onMouseDown={event=>{if(event.target===event.currentTarget)onClose()}}><section ref={dialog} tabIndex={-1} className="evidence-modal" role="dialog" aria-modal="true" aria-label={source.title}>
  <header className="evidence-head"><div><h2>{source.title}</h2>{source.summary!==source.title&&<p>{source.summary}</p>}</div><button className="button ghost" onClick={onClose} aria-label="Close evidence">Close</button></header>
  <div className="evidence-body">{source.finding&&<><p>{source.finding.explanation}</p><Chart data={source.finding.series} percent lines={[{key:'actual_share',label:'Actual share of demand',color:'#205a4e'},{key:'expected_share',label:'Expected for the weather',color:'#a695bf',dashed:true}]}/></>}
   {drilldown&&<CohortDrilldown data={drilldown}/>}
   {sections.length>0&&<><div className="evidence-toolbar"><label>Section<select value={section} onChange={event=>{setSection(Number(event.target.value));setPage(0);setSort('')}}>{sections.map((item,index)=><option key={index} value={index}>{item.name} · {item.rows.length}</option>)}</select></label><label>Search rows<input type="search" value={search} onChange={event=>{setSearch(event.target.value);setPage(0)}} placeholder="Search saved rows"/></label></div>
   <div className="evidence-table-wrap"><table><thead><tr>{columns.map(key=><th key={key} scope="col" aria-sort={sort===key?(descending?'descending':'ascending'):'none'}><button onClick={()=>{setDescending(sort===key?!descending:false);setSort(key);setPage(0)}} aria-label={`Sort by ${label(key)}`}>{label(key)}{sort===key?(descending?' ↓':' ↑'):''}</button></th>)}</tr></thead><tbody>{rows.slice(page*25,(page+1)*25).map((row,index)=><tr key={index}>{columns.map(key=><td key={key}>{cell(row[key])}</td>)}</tr>)}</tbody></table>{!rows.length&&<p className="muted">No rows match this search.</p>}</div><div className="evidence-pagination"><span>{rows.length} rows · Page {page+1} of {pages}</span><button className="button ghost" disabled={page===0} onClick={()=>setPage(page-1)}>Previous</button><button className="button ghost" disabled={page>=pages-1} onClick={()=>setPage(page+1)}>Next</button></div></>}
   <details><summary>Saved query and method</summary><DataView value={{arguments:source.args,method:source.method}}/></details>
   <details><summary>Full saved result</summary><pre className="evidence-raw">{savedResult}</pre></details>
  </div><footer className="evidence-footer"><a href={evidenceUrl(planId,source.id)} target="_blank" rel="noopener noreferrer">Open in new tab</a><button className="button primary" onClick={onClose}>Back to report</button></footer>
 </section></div>;
}
