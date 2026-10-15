import { useEffect, useRef, useState } from 'react';
import { api, n } from './api';
import { Chart, DataView, Icon } from './ui';
import type { CohortCard, Detail, DirectionPreview } from './types';
import './cohortCards.css';
import { ProductIcon } from './ProductIcon';
import { EditReceipt, type PlanEdit } from './EditReceipt';
import { CohortDrilldown } from './CohortDrilldown';

type Override = { id:number|string; type:string; value:unknown; note?:string; tag_path?:{id:string;included:boolean}[]; districts?:string[]; sku?:string };
type Cohorts = { cards:CohortCard[]; method:unknown; overrides:Override[] };
type Edit = PlanEdit;
const signed = (v:number, digits=1) => `${v>0?'+':''}${n(v,digits)}`;

export function CohortCards({detail,revision,onChanged}:{detail:Detail;revision:number;onChanged:()=>void}) {
  const [data,setData]=useState<Cohorts|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[edit,setEdit]=useState<Edit|null>(null);
  useEffect(()=>{const latest=[...detail.decisions].reverse().find(d=>['set_override','bulk_edit_orders','goal_edit'].includes(d.key)&&!(d.value as {undone_at?:string})?.undone_at);if(latest){const value=latest.value as Edit;setEdit({edit_id:Number(latest.id),affected_orders:value.affected_orders})}else setEdit(null)},[detail.decisions]);
  const [service,setService]=useState<number|null>(detail.plan.service_level);
  const [preview,setPreview]=useState<DirectionPreview|null>(null),[autoService,setAutoService]=useState<number|null>(null),[previewError,setPreviewError]=useState(''),[previewPending,setPreviewPending]=useState(true);
  const previewSequence=useRef(0),highlightTimer=useRef<ReturnType<typeof setTimeout>|null>(null),panel=useRef<HTMLElement>(null);
  const path=`/plans/${encodeURIComponent(detail.plan.id)}`;
  useEffect(()=>{setService(detail.plan.service_level)},[detail.plan.service_level]);
  useEffect(()=>{let active=true;setError('');api<Cohorts>(`${path}/cohorts`).then(value=>{if(active)setData(value)}).catch(e=>{if(active)setError((e as Error).message)});return()=>{active=false}},[path,revision]);
  useEffect(()=>{
    const sequence=++previewSequence.current;
    setPreviewPending(true);setPreviewError('');
    const timer=setTimeout(()=>{
      api<DirectionPreview>(`${path}/direction-preview`,'POST',{service_level:service})
        .then(value=>{if(sequence===previewSequence.current){setPreview(value);setAutoService(value.auto_service_level);setPreviewPending(false)}})
        .catch(e=>{if(sequence===previewSequence.current){setPreviewError((e as Error).message);setPreviewPending(false)}});
    },150);
    return()=>{clearTimeout(timer);previewSequence.current++};
  },[path,service,revision]);
  useEffect(()=>{
    const focus=(event:Event)=>{
      const id=(event as CustomEvent<{id?:string}>).detail?.id;
      if(!id)return;
      const card=Array.from(panel.current?.querySelectorAll<HTMLElement>('[data-cohort-id]')||[]).find(item=>item.dataset.cohortId===id);
      if(!card)return;
      if(highlightTimer.current)clearTimeout(highlightTimer.current);
      panel.current?.querySelectorAll('.is-highlighted').forEach(item=>item.classList.remove('is-highlighted'));
      card.scrollIntoView({block:'nearest',behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});
      card.focus({preventScroll:true});card.classList.add('is-highlighted');
      highlightTimer.current=setTimeout(()=>card.classList.remove('is-highlighted'),2400);
    };
    window.addEventListener('scoop:focus-cohort',focus);
    return()=>{window.removeEventListener('scoop:focus-cohort',focus);if(highlightTimer.current)clearTimeout(highlightTimer.current)};
  },[]);
  async function applyOverride(card:CohortCard,type:string,value:unknown,note:string){
    setBusy(true);setError('');
    try{const result=await api<Edit>(`${path}/overrides`,'POST',{cohort:card.id,type,value,note});setEdit(result);onChanged()}
    catch(e){setError((e as Error).message)}finally{setBusy(false)}
  }
  async function saveService(){if(!preview||previewPending||previewError||preview.service_level!==service)return;setBusy(true);setError('');try{await api(`${path}/goal`,'PUT',{goal:detail.plan.goal,service_level:service});onChanged()}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
  const shownService=service??autoService??0.5;
  const peak=preview?.projected_peak_pallets??0,capacity=preview?.capacity_pallets??0,excess=Math.max(0,peak-capacity);
  return <aside ref={panel} className="cohort-panel" aria-label="This week's direction">
    <h2>This week's direction</h2>
    <div className="cohort-service"><div className="cohort-service-heading"><label htmlFor="cohort-service">In-stock target</label><strong>{service===null&&autoService===null?'—':`${n(shownService*100,1)}%`}{service===null&&<span> · auto</span>}</strong></div><input id="cohort-service" type="range" min="0.5" max="0.98" step="0.005" value={shownService} onChange={e=>setService(Number(e.target.value))} disabled={busy||(service===null&&autoService===null&&!previewError)} aria-valuetext={service===null&&autoService===null?'Automatic target loading':`${n(shownService*100,1)} percent${service===null?', automatic':''}`}/><div className="cohort-service-ends"><span>Save space</span><span>Avoid stockouts</span></div>{service!==null&&<button type="button" className="text-button cohort-reset" onClick={()=>setService(null)} disabled={busy}>Reset to auto</button>}
      <div className="cohort-preview-row"><p aria-live="polite">{previewError?'Preview unavailable':preview?`${n(preview.cases)} cases this week · cold-store peak ${n(peak,1)} of ${n(capacity,1)} pallets${previewPending?' · updating…':''}`:previewPending?'Updating preview…':'Preview unavailable'}</p><button type="button" className="button primary" onClick={saveService} disabled={busy||previewPending||!!previewError||!preview||preview.service_level!==service||service===detail.plan.service_level}>Apply</button></div>
      {excess>0.05&&preview&&!previewPending&&!previewError&&<p className="cohort-excess" role="status">⚠ {n(excess,1)} pallets over, {preview.incremental_excess_pallets>0.05?`${n(preview.incremental_excess_pallets,1)} from new purchases`:'all from stock already on hand or inbound'}</p>}
      {previewError&&<p className="cohort-error" role="alert">{previewError}</p>}
    </div>
    {error&&<p className="cohort-error" role="alert">{error}</p>}
    {edit&&<EditReceipt key={edit.edit_id} edit={edit} detail={detail} path={path} onChanged={onChanged} disabled={busy}/>}
    <h2>Demand changes</h2>
    {!data&&!error&&<p className="cohort-muted">Loading changes…</p>}
    {data?.cards.length===0&&<p className="cohort-muted">No demand changes to review this week.</p>}
    {data?.cards.map(card=><CohortCardView key={card.id} card={card} overrides={data.overrides.filter(item=>card.override_ids?.includes(item.id))} busy={busy} apply={applyOverride}/>)}
    {data&&<details className="cohort-method"><summary>Full method trace</summary><DataView value={data.method}/></details>}
  </aside>;
}

function CohortCardView({card,overrides,busy,apply}:{card:CohortCard;overrides:Override[];busy:boolean;apply:(card:CohortCard,type:string,value:unknown,note:string)=>Promise<void>}){
  const context=overrides.filter(item=>item.type!=='cases'),caseEdits=overrides.length-context.length;
  const [expanded,setExpanded]=useState(false),[howOpen,setHowOpen]=useState(false),[days,setDays]=useState(14);
  const [type,setType]=useState('one_off'),[pct,setPct]=useState('30'),[strength,setStrength]=useState('medium'),[endsOn,setEndsOn]=useState(''),[sku,setSku]=useState(card.skus[0]||''),[cases,setCases]=useState(''),[note,setNote]=useState('');
  const value=type==='one_off'?true:type==='ends_on'?endsOn:type==='cap'?Number(pct)/100:type==='expect'?{pct:Number(pct)/100,strength}:{sku,cases:Number(cases)};
  const valid=type==='one_off'||type==='ends_on'&&!!endsOn||type==='cap'&&Number(pct)>-100||type==='expect'&&Number(pct)>-100||type==='cases'&&!!sku&&cases!==''&&Number.isInteger(Number(cases))&&Number(cases)>=0;
  const paths=card.tag_path.map((term,index)=>card.drilldown?.steps[index]?.label||`${term.included?'':'Not '}${term.id.split(':').at(-1)?.replaceAll('_',' ')||term.id}`);
  return <article className="cohort-card" data-cohort-id={card.id} tabIndex={-1}><header><div className="cohort-heading">{card.representative_sku&&<ProductIcon sku={card.representative_sku} size={48} decorative/>}<div><h3>{card.name}</h3><p className="cohort-effect">Demand {card.effect_pct>0?`+${n(Math.abs(card.effect_pct),0)}% above forecast`:card.effect_pct<0?`${n(Math.abs(card.effect_pct),0)}% below forecast`:'in line with forecast'}</p></div></div><button className="icon-button" aria-label={`${expanded?'Collapse':'Expand'} ${card.name} trend`} aria-expanded={expanded} onClick={()=>setExpanded(v=>!v)}><Icon name={expanded?'close':'arrow'} size={18}/></button></header>
    {paths.length>0&&<p className="cohort-path">{paths.map((path,index)=><span key={index}>{path}</span>)}</p>}
    <div className="cohort-numbers"><span className="cohort-direction" aria-hidden="true">{card.case_change>0?'+':card.case_change<0?'−':'Ⅱ'}</span><div><strong className="cohort-key">{card.case_change>0?`+${n(card.case_change,0)} cases added to this week's order`:card.case_change<0?`${n(Math.abs(card.case_change),0)} cases reduced in this week's order`:'This week’s order unchanged'}</strong><p className="cohort-impact">{signed(card.pallet_change,1)} pallets · HK${n(Math.abs(card.expected_lost_margin_avoided))} {card.expected_lost_margin_avoided<0?'extra margin lost':'lost margin avoided'}</p></div></div>
    {card.peak_capacity!=null&&<p className={`cohort-capacity ${card.capacity_pallets!=null&&card.peak_capacity>card.capacity_pallets?'over':''}`}>Cold-store peak {n(card.peak_capacity,1)}{card.capacity_pallets!=null?` of ${n(card.capacity_pallets,1)}`:''} pallets</p>}
    {expanded&&!howOpen&&<div className="cohort-chart"><label>Time range<select value={days} onChange={e=>setDays(Number(e.target.value))}>{[7,14,28,70].map(value=><option key={value} value={value}>{value} days</option>)}</select></label><Chart data={(card.daily||[]).slice(-days)} lines={[{key:'requested_units',label:'Requested',color:'#205a4e'},{key:'expected_units',label:'Expected',color:'#91a398',dashed:true}]}/><p className="cohort-muted">{card.series_scope}</p></div>}
    {card.drilldown&&<details className="cohort-how" onToggle={event=>setHowOpen(event.currentTarget.open)}><summary>How we found it</summary><CohortDrilldown data={card.drilldown}/></details>}
    <details><summary>Evidence and products</summary><div className="cohort-details"><p>80% effect interval: {signed(card.interval_pct[0])}% to {signed(card.interval_pct[1])}%</p><p>Definition: {card.tag_path.map(term=>`${term.included?'':'not '}${term.id}`).join(' · ')||'All products'}{card.districts.length?` · ${card.districts.join(', ')}`:''}</p><div className="cohort-table-wrap"><table><thead><tr><th>Product</th><th>Factor (10 / 50 / 90)</th><th>Cases</th><th>Change</th></tr></thead><tbody>{(card.sku_factors||[]).map(row=><tr key={row.sku}><th scope="row">{row.name}</th><td>{n(row.f10,2)} / {n(row.f50,2)} / {n(row.f90,2)}</td><td>{n(row.cases)}</td><td>{signed(row.case_change,0)}</td></tr>)}</tbody></table></div><details><summary>How it was calculated</summary><DataView value={card.method}/></details></div></details>
    {context.length>0&&<p className="cohort-overrides">Active context: {context.map(item=>`${item.type.replaceAll('_',' ')}${item.note?` · ${item.note}`:''}`).join('; ')}</p>}
    {caseEdits>0&&<p className="cohort-overrides">{caseEdits} order quantities edited</p>}
    <details className="cohort-context"><summary>Add context</summary><div><label>Context<select value={type} onChange={e=>setType(e.target.value)} disabled={busy}><option value="one_off">One-off</option><option value="ends_on">Ends on</option><option value="cap">Cap change</option><option value="expect">Expect change</option><option value="cases">Set cases</option></select></label>
      {type==='ends_on'&&<label>Ends before<input type="date" value={endsOn} onChange={e=>setEndsOn(e.target.value)} disabled={busy}/></label>}
      {(type==='cap'||type==='expect')&&<label>{type==='cap'?'Maximum change':'Expected change'} (%)<input type="number" step="0.1" min="-99" value={pct} onChange={e=>setPct(e.target.value)} disabled={busy}/></label>}
      {type==='expect'&&<label>Confidence<select value={strength} onChange={e=>setStrength(e.target.value)} disabled={busy}><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option></select></label>}
      {type==='cases'&&<><label>Product<select value={sku} onChange={e=>setSku(e.target.value)} disabled={busy}>{(card.sku_factors||[]).map(row=><option key={row.sku} value={row.sku}>{row.name}</option>)}</select></label><label>Cases<input type="number" min="0" step="1" value={cases} onChange={e=>setCases(e.target.value)} disabled={busy}/></label></>}
      <label>Note (optional)<input value={note} onChange={e=>setNote(e.target.value)} disabled={busy}/></label><button type="button" className="button ghost" disabled={busy||!valid} onClick={()=>apply(card,type,value,note)}>Apply context</button></div></details>
  </article>;
}
