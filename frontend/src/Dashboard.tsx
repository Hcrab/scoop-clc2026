import { useEffect, useMemo, useRef, useState, type DragEvent } from 'react';
import { api, date, n, pct } from './api';
import { EditReceipt, type PlanEdit } from './EditReceipt';
import type { DashboardData, DashboardMetric, DashboardScope, DashboardSpec, DashboardWidget, Detail, Product } from './types';
import { Chart, Icon, Modal } from './ui';
import './dashboard.css';

export type PlayRun = {daily:{pallets_pre_ship:number;pallets:number}[];per_sku:{on_hand:number[][];shipped:number[][];lost:number[][];arrived:number[][]};expected?:(number|null)[][]};
export type DashboardPlay = {dates:string[];skus:string[];demand:number[][];expected?:(number|null)[][];runs:{scoop:PlayRun;baseline:PlayRun};capacity_pallets:number};
const metrics:{id:DashboardMetric;label:string}[] = [
  {id:'on_hand',label:'Stock on hand'},{id:'lost_units',label:'Units short'},
  {id:'demand',label:'Store requests'},{id:'fill_rate',label:'Fill rate'},
  {id:'days_cover',label:'Days of cover'},{id:'pallets',label:'Cold store pallets'},
  {id:'requested_vs_expected',label:'Requested vs expected'},
];
const format=(value:number|null|undefined,unit:DashboardWidget['unit'])=>unit==='ratio'?pct(value):unit==='days'?`${n(value,1)} days`:unit==='pallets'?`${n(value,1)} pallets`:`${n(value)} units`;
const label=(w:DashboardWidget, data:DashboardData)=>data.options.find(o=>o.kind===w.scope.kind&&o.key===w.scope.key)?.label || (w.scope.kind==='warehouse'?'Whole warehouse':w.scope.key||w.scope.kind);
const receipt=(value:unknown, name:string):PlanEdit=>({...value as PlanEdit,label:name});

function forward(result:DashboardPlay, widget:DashboardWidget, policy:'scoop'|'baseline', products:Product[]):{values:(number|null)[];expected?:(number|null)[]} {
  const run=result.runs[policy];
  const included=new Set(widget.skus);
  const indexes=result.skus.map((sku,i)=>included.has(sku)?i:-1).filter(i=>i>=0);
  const sum=(rows:number[][])=>rows.map(row=>indexes.reduce((total,i)=>total+(row?.[i]||0),0));
  const demand=sum(result.demand),shipped=sum(run.per_sku.shipped),stock=sum(run.per_sku.on_hand),lost=sum(run.per_sku.lost);
  if(widget.metric==='on_hand')return {values:stock};
  if(widget.metric==='lost_units')return {values:lost};
  if(widget.metric==='demand')return {values:demand};
  if(widget.metric==='fill_rate')return {values:demand.map((d,i)=>d?shipped[i]/d:null)};
  if(widget.metric==='days_cover')return {values:stock.map((s,i)=>{const history=(widget.recent_demand||[]).filter(point=>point.date<result.dates[0]).map(point=>point.value);const recent=[...history,...demand.slice(0,i)].slice(-7);if(recent.length!==7||recent.some(value=>value==null))return null;const average=recent.reduce<number>((a,b)=>a+(b||0),0)/7;return average>0?s/average:null})};
  if(widget.metric==='pallets'){
    const footprints=new Map(products.map(p=>[p.sku,p.units_per_case*p.cases_per_pallet]));
    return {values:run.per_sku.on_hand.map(row=>indexes.reduce((total,i)=>total+(row?.[i]||0)/(footprints.get(result.skus[i])||Infinity),0))};
  }
  const grid=result.expected||run.expected;
  const expected=grid?.map(row=>indexes.length&&indexes.every(index=>row?.[index]!=null)?indexes.reduce((total,index)=>total+(row[index] as number),0):null);
  return {values:demand,expected};
}

function WidgetChart({widget,result,day,products}:{widget:DashboardWidget;result?:DashboardPlay|null;day:number;products:Product[]}) {
  const past=widget.series.map(point=>({date:point.date,plan:point.value??NaN,expected:point.expected??NaN,rule:NaN,dot:NaN}));
  const plan=result&&day>=0?forward(result,widget,'scoop',products):null;
  const rule=result&&day>=0?forward(result,widget,'baseline',products):null;
  const future=result&&plan&&rule?result.dates.slice(0,day+1).map((at,i)=>({date:at,plan:plan.values[i]??NaN,rule:rule.values[i]??NaN,expected:plan.expected?.[i]??NaN,dot:widget.skus.some(sku=>{const index=result.skus.indexOf(sku);return index>=0&&(result.runs.baseline.per_sku.lost[i]?.[index]||0)>0})?rule.values[i]??NaN:NaN})):[];
  const data=[...past,...future];
  const hasExpected=data.some(row=>Number.isFinite(row.expected));
  const latest=future.at(-1)?.plan;
  const value=result&&day>=0?(latest!=null&&Number.isFinite(latest)?latest:null):widget.value;
  const state=value==null?'unknown':widget.threshold?((widget.threshold.operator==='lt'?value<widget.threshold.value:value>widget.threshold.value)?'warning':'normal'):'normal';
  return <><strong className="dashboard-value">{value==null?'Not available':format(value,widget.unit)}</strong>{widget.threshold&&<small className={`dashboard-current-state ${state}`}>{state==='warning'?'Alert':state==='unknown'?'Threshold unavailable':'Within threshold'}</small>}{data.some(row=>Number.isFinite(row.plan))?<Chart small data={data} percent={widget.unit==='ratio'} lines={[{key:'plan',label:result&&day>=0?'This plan':'Recorded',color:'#205a4e'},{key:'rule',label:'Moving-average rule',color:'#b28a5a'},{key:'dot',label:'Rule stockout',color:'#c96c59',dots:true},...(hasExpected?[{key:'expected',label:'Expected',color:'#8f87a6',dashed:true}]:[])]}/>:<p className="muted">No recorded history yet.</p>}</>;
}

function Editor({item,data,path,close,saved}:{item?:DashboardWidget;data:DashboardData;path:string;close:()=>void;saved:(value:unknown,name:string)=>void}) {
  const [scope,setScope]=useState<DashboardScope>(item?.scope||{kind:'warehouse'});
  const [metric,setMetric]=useState<DashboardMetric>(item?.metric||'on_hand');
  const [title,setTitle]=useState(item?.title||'Stock on hand');
  const [operator,setOperator]=useState<'lt'|'gt'|''>(item?.threshold?.operator||'');
  const [threshold,setThreshold]=useState(item?.threshold?.value==null?'':String(item.threshold.value));
  const [preview,setPreview]=useState<DashboardWidget|null>(null);
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  const options=data.options.length?data.options:[{kind:'warehouse' as const,label:'Whole warehouse'}];
  const chosen=options.find(o=>o.kind===scope.kind&&o.key===scope.key)||options[0];
  const spec=useMemo<DashboardSpec>(()=>({title:title.trim(),scope:chosen.key?{kind:chosen.kind,key:chosen.key}:{kind:chosen.kind},metric,threshold:operator&&threshold!==''?{operator,value:Number(threshold)}:null}),[title,chosen.kind,chosen.key,metric,operator,threshold]);
  const valid=!!spec.title&&(!operator||(threshold!==''&&Number.isFinite(Number(threshold))));
  useEffect(()=>{if(!valid){setPreview(null);return}const controller=new AbortController();const t=setTimeout(()=>{api<DashboardWidget>(`${path}/dashboard-preview`,'POST',spec).then(value=>{if(!controller.signal.aborted){setPreview(value);setError('')}}).catch(e=>{if(!controller.signal.aborted){setPreview(null);setError((e as Error).message)}})},250);return()=>{controller.abort();clearTimeout(t)}},[path,spec,valid]);
  async function save(){if(!valid||busy)return;setBusy(true);setError('');try{const response=await api(`${path}/dashboard${item?`/${encodeURIComponent(item.id)}`:''}`,item?'PUT':'POST',spec);saved(response,item?'Widget updated':'Widget added');close()}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
  return <Modal title={item?'Edit widget':'Add widget'} onClose={close}><div className="dashboard-editor">
    <label className="field">Scope<select value={`${chosen.kind}:${chosen.key||''}`} onChange={e=>{const picked=options.find(o=>`${o.kind}:${o.key||''}`===e.target.value)!;setScope(picked.key?{kind:picked.kind,key:picked.key}:{kind:picked.kind})}}>{options.map(o=><option key={`${o.kind}:${o.key||''}`} value={`${o.kind}:${o.key||''}`}>{o.label}</option>)}</select></label>
    <label className="field">Measure<select value={metric} onChange={e=>{const next=e.target.value as DashboardMetric;setMetric(next);if(!item||title===metrics.find(m=>m.id===metric)?.label)setTitle(metrics.find(m=>m.id===next)!.label)}}>{metrics.map(m=><option key={m.id} value={m.id}>{m.label}</option>)}</select></label>
    <label className="field">Title<input value={title} onChange={e=>setTitle(e.target.value)}/></label>
    <div className="dashboard-threshold"><label className="field">Alert when<select value={operator} onChange={e=>setOperator(e.target.value as 'lt'|'gt'|'')}><option value="">No threshold</option><option value="lt">Below</option><option value="gt">Above</option></select></label>{operator&&<label className="field">Value<input type="number" step="any" value={threshold} onChange={e=>setThreshold(e.target.value)}/></label>}</div>
    <div className="dashboard-preview"><span>Preview</span>{preview?<><strong>{format(preview.value,preview.unit)}</strong><small>{preview.series.length?`${date(preview.series[0].date)} – ${date(preview.series.at(-1)!.date)}`:'No recorded history yet'}</small></>:<small>{valid?'Loading preview…':'Enter a title and threshold value.'}</small>}</div>
    {error&&<p role="alert" className="chat-error">{error}</p>}
  </div><div className="modal-actions"><button className="button ghost" onClick={close}>Cancel</button><button className="button primary" disabled={!valid||busy||!preview} onClick={save}>{busy?'Saving…':item?'Save widget':'Add widget'}</button></div></Modal>;
}

export function Dashboard({detail,products,path,result,day=-1,pending=false,readonly=false,revision=0,onChanged}:{detail:Detail;products:Product[];path:string;result?:DashboardPlay|null;day?:number;pending?:boolean;readonly?:boolean;revision?:number;onChanged?:()=>void}) {
  const [data,setData]=useState<DashboardData|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  const [editing,setEditing]=useState<DashboardWidget|null|undefined>(),[edit,setEdit]=useState<PlanEdit|null>(null);
  const dragged=useRef<string|null>(null);
  async function refresh(){try{setData(await api<DashboardData>(`${path}/dashboard`));setError('')}catch(e){setError((e as Error).message)}}
  useEffect(()=>{setData(null);setEdit(null);void refresh()},[path]);
  useEffect(()=>{if(data)void refresh()},[revision]);
  function changed(response:unknown,name:string){setEdit(receipt(response,name));void refresh();onChanged?.()}
  async function remove(widget:DashboardWidget){if(busy)return;setBusy(true);try{changed(await api(`${path}/dashboard/${encodeURIComponent(widget.id)}`,'DELETE'),`Removed ${widget.title}`)}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
  async function move(id:string,delta:number){if(!data||busy)return;const ids=data.widgets.map(w=>w.id),from=ids.indexOf(id),to=from+delta;if(from<0||to<0||to>=ids.length)return;ids.splice(from,1);ids.splice(to,0,id);await reorder(ids)}
  async function reorder(ids:string[]){if(!data||busy||ids.every((id,i)=>id===data.widgets[i]?.id))return;setBusy(true);try{changed(await api(`${path}/dashboard-layout`,'PUT',{ids}),'Dashboard reordered')}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
  function drop(before?:string){const id=dragged.current;dragged.current=null;if(!id||!data)return;const ids=data.widgets.map(w=>w.id).filter(x=>x!==id),at=before?ids.indexOf(before):-1;ids.splice(at<0?ids.length:at,0,id);void reorder(ids)}
  const disabled=readonly||pending||busy;
  return <section className="dashboard" aria-label="Dashboard"><header className="dashboard-heading"><div><h2>Dashboard</h2>{data?.facts_through&&<small>Recorded through {date(data.facts_through)}</small>}</div>{!readonly&&<button className="button ghost" disabled={disabled} onClick={()=>setEditing(null)}><Icon name="plus" size={16}/>Add widget</button>}</header>
    {error&&<p role="alert" className="chat-error">{error}</p>}
    {!data&&!error&&<p className="muted">Loading dashboard…</p>}
    {data&&!data.widgets.length&&<p className="muted">No widgets yet. Add a measure to follow.</p>}
    <div className="dashboard-grid" onDragOver={e=>e.preventDefault()} onDrop={()=>drop()}>{data?.widgets.map((widget,index)=>{const value=result&&day>=0?forward(result,widget,'scoop',products).values[day]:widget.value;const state=value==null?'unknown':widget.threshold?((widget.threshold.operator==='lt'?value<widget.threshold.value:value>widget.threshold.value)?'warning':'normal'):'normal';return <article key={widget.id} className={`dashboard-widget ${state==='warning'?'warning':''}`} draggable={!disabled} onDragStart={(e:DragEvent)=>{dragged.current=widget.id;e.dataTransfer.effectAllowed='move'}} onDragOver={e=>e.preventDefault()} onDrop={e=>{e.stopPropagation();drop(widget.id)}}><header><div><h3>{widget.title}</h3><small>{label(widget,data)}{widget.threshold?` · ${widget.threshold.operator==='lt'?'Below':'Above'} ${format(widget.threshold.value,widget.unit)}`:''}</small></div>{state==='warning'&&<span className="dashboard-warning">Alert</span>}</header><WidgetChart widget={widget} result={result} day={day} products={products}/>{!readonly&&<div className="dashboard-actions"><button className="text-button" disabled={disabled||index===0} aria-label={`Move ${widget.title} up`} onClick={()=>move(widget.id,-1)}>↑</button><button className="text-button" disabled={disabled||index===data.widgets.length-1} aria-label={`Move ${widget.title} down`} onClick={()=>move(widget.id,1)}>↓</button><button className="text-button" disabled={disabled} onClick={()=>setEditing(widget)}>Edit</button><button className="text-button" disabled={disabled} onClick={()=>remove(widget)}>Remove</button></div>}</article>})}</div>
    {edit&&<EditReceipt key={edit.edit_id} edit={edit} detail={detail} path={path} onChanged={()=>{void refresh();onChanged?.()}} disabled={disabled}/>}
    {editing!==undefined&&data&&<Editor item={editing||undefined} data={data} path={path} close={()=>setEditing(undefined)} saved={changed}/>}
  </section>;
}
