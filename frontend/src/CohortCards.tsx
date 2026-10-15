import { useEffect, useState } from 'react';
import { api, n } from './api';
import { Chart, DataView, Icon } from './ui';
import type { CohortCard, Detail } from './types';
import './cohortCards.css';
import { EditReceipt, type PlanEdit } from './EditReceipt';

type Override = { id:number|string; type:string; value:unknown; note?:string; tag_path?:{id:string;included:boolean}[]; districts?:string[]; sku?:string };
type Cohorts = { cards:CohortCard[]; method:unknown; overrides:Override[] };
type Edit = PlanEdit;
const signed = (v:number, digits=1) => `${v>0?'+':''}${n(v,digits)}`;

export function CohortCards({detail,revision,onChanged}:{detail:Detail;revision:number;onChanged:()=>void}) {
  const [data,setData]=useState<Cohorts|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[edit,setEdit]=useState<Edit|null>(null);
  useEffect(()=>{const latest=[...detail.decisions].reverse().find(d=>['set_override','bulk_edit_orders','goal_edit'].includes(d.key)&&!(d.value as {undone_at?:string})?.undone_at);if(latest){const value=latest.value as Edit;setEdit({edit_id:Number(latest.id),affected_orders:value.affected_orders})}else setEdit(null)},[detail.decisions]);
  const [service,setService]=useState(detail.plan.service_level==null?'':String(detail.plan.service_level*100));
  const path=`/plans/${encodeURIComponent(detail.plan.id)}`;
  useEffect(()=>{setService(detail.plan.service_level==null?'':String(detail.plan.service_level*100))},[detail.plan.service_level]);
  useEffect(()=>{let active=true;setData(null);setError('');api<Cohorts>(`${path}/cohorts`).then(value=>{if(active)setData(value)}).catch(e=>{if(active)setError((e as Error).message)});return()=>{active=false}},[path,revision]);
  async function applyOverride(card:CohortCard,type:string,value:unknown,note:string){
    setBusy(true);setError('');
    try{const result=await api<Edit>(`${path}/overrides`,'POST',{cohort:card.id,type,value,note});setEdit(result);onChanged()}
    catch(e){setError((e as Error).message)}finally{setBusy(false)}
  }
  async function saveService(){setBusy(true);setError('');try{await api(`${path}/goal`,'PUT',{goal:detail.plan.goal,service_level:service===''?null:Number(service)/100});onChanged()}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
  return <aside className="cohort-panel" aria-label="Demand changes and context">
    <div className="cohort-service"><h2>Stock and space</h2><label htmlFor="cohort-service">Fewer stockouts ⟷ Less space</label><div className="cohort-service-control"><input id="cohort-service" type="range" min="50" max="98" step="0.5" value={service?String(148-Number(service)):'74'} onChange={e=>setService(String(148-Number(e.target.value)))} disabled={busy}/><strong>{service?`${n(Number(service),1)}%`:'Auto'}</strong><button type="button" className="button ghost" onClick={saveService} disabled={busy||service!==''&&(Number(service)<50||Number(service)>98)}>Apply</button></div></div>
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
  const [expanded,setExpanded]=useState(false),[days,setDays]=useState(14);
  const [type,setType]=useState('one_off'),[pct,setPct]=useState('30'),[strength,setStrength]=useState('medium'),[endsOn,setEndsOn]=useState(''),[sku,setSku]=useState(card.skus[0]||''),[cases,setCases]=useState(''),[note,setNote]=useState('');
  const value=type==='one_off'?true:type==='ends_on'?endsOn:type==='cap'?Number(pct)/100:type==='expect'?{pct:Number(pct)/100,strength}:{sku,cases:Number(cases)};
  const valid=type==='one_off'||type==='ends_on'&&!!endsOn||type==='cap'&&Number(pct)>-100||type==='expect'&&Number(pct)>-100||type==='cases'&&!!sku&&cases!==''&&Number.isInteger(Number(cases))&&Number(cases)>=0;
  return <article className="cohort-card"><header><div><h3>{card.name}</h3><p className="cohort-effect">{signed(card.effect_pct)}% estimated change</p></div><button className="icon-button" aria-label={`${expanded?'Collapse':'Expand'} ${card.name} trend`} aria-expanded={expanded} onClick={()=>setExpanded(v=>!v)}><Icon name={expanded?'close':'arrow'} size={18}/></button></header>
    <div className="cohort-numbers"><span className="cohort-direction" aria-hidden="true">{card.case_change>0?'+':card.case_change<0?'−':'Ⅱ'}</span><div><strong className="cohort-key">{signed(card.case_change,0)}<span> cases</span></strong><p className="cohort-impact">{signed(card.pallet_change,1)} pallets · HK${n(Math.abs(card.expected_lost_margin_avoided))} {card.expected_lost_margin_avoided<0?'extra margin lost':'lost margin avoided'}</p></div></div>
    {card.peak_capacity!=null&&<p className="cohort-capacity">Peak capacity {n(card.peak_capacity,1)}{card.capacity_pallets!=null?` / ${n(card.capacity_pallets)}`:''} pallets</p>}
    {expanded&&<div className="cohort-chart"><label>Time range<select value={days} onChange={e=>setDays(Number(e.target.value))}>{[7,14,28,70].map(value=><option key={value} value={value}>{value} days</option>)}</select></label><Chart data={(card.daily||[]).slice(-days)} lines={[{key:'requested_units',label:'Requested',color:'#205a4e'},{key:'expected_units',label:'Expected',color:'#91a398',dashed:true}]}/><p className="cohort-muted">{card.series_scope}</p></div>}
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
