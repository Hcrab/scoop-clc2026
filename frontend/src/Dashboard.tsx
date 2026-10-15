import { useEffect, useMemo, useRef, useState, type DragEvent } from 'react';
import { api, date, n, pct } from './api';
import { EditReceipt, type PlanEdit } from './EditReceipt';
import type { DashboardData, DashboardMetric, DashboardScope, DashboardSpec, DashboardWidget, Detail, Product } from './types';
import { Chart, Icon, Modal } from './ui';
import { widgetHourPoint, widgetPoint } from './replayData';
import './dashboard.css';

export type HourlyRun = {on_hand:number[][];on_hand_delta:number[][];demand:number[][];shipped:number[][];lost:number[][];arrived:number[][]};
export type PlayRun = {daily:{pallets_pre_ship:number;pallets:number}[];per_sku:{on_hand:number[][];shipped:number[][];lost:number[][];arrived:number[][]};hourly:HourlyRun;expected?:(number|null)[][]};
export type DashboardPlay = {dates:string[];skus:string[];demand:number[][];expected?:(number|null)[][];intraday:{step_minutes:10;minutes:number[];demand_cdf:number[];dispatch_cdf:number[];arrival_minutes:number[][];opening_on_hand:number[]};runs:{scoop:PlayRun;baseline:PlayRun};capacity_pallets:number};
const metrics:{id:DashboardMetric;label:string}[] = [
  {id:'on_hand',label:'Stock on hand'},{id:'lost_units',label:'Units short'},
  {id:'demand',label:'Store requests'},{id:'fill_rate',label:'Fill rate'},
  {id:'days_cover',label:'Days of cover'},{id:'pallets',label:'Cold store pallets'},
  {id:'requested_vs_expected',label:'Requested vs expected'},
];
const format=(value:number|null|undefined,unit:DashboardWidget['unit'])=>unit==='ratio'?pct(value):unit==='days'?`${n(value,1)} days`:unit==='pallets'?`${n(value,1)} pallets`:`${n(value)} units`;
const label=(w:DashboardWidget, data:DashboardData)=>data.options.find(o=>o.kind===w.scope.kind&&o.key===w.scope.key)?.label || (w.scope.kind==='warehouse'?'Whole warehouse':w.scope.key||w.scope.kind);
type NamedCohort = {id:string;tag_path:{id:string;included:boolean}[];districts:string[]};
function widgetTitle(widget:DashboardWidget, data:DashboardData, detail:Detail) {
  if (widget.scope.kind !== 'cohort' || widget.metric !== 'requested_vs_expected' || !widget.title.endsWith(' requests')) return widget.title;
  const card = (detail as Detail & {cohort_cards?:NamedCohort[]}).cohort_cards?.find(item=>item.id===widget.scope.key);
  if (!card) return widget.title;
  const oldParts = card.tag_path.filter(term=>!term.id.startsWith('district:')).map(term=>`${term.included?'':'Not '}${data.options.find(option=>option.kind==='tag'&&option.key===term.id)?.label||term.id}`);
  if (card.tag_path.some(term=>term.id.startsWith('district:'))) oldParts.push(card.districts.join(', '));
  const savedParts = widget.title.slice(0,-' requests'.length).split(' · ');
  oldParts.sort();savedParts.sort();
  return oldParts.length === savedParts.length && oldParts.every((part,index)=>part===savedParts[index]) ? `${label(widget,data)} requests` : widget.title;
}
const receipt=(value:unknown, name:string):PlanEdit=>({...value as PlanEdit,label:name});

function WidgetChart({widget,result,day,minute,products}:{widget:DashboardWidget;result?:DashboardPlay|null;day:number;minute:number|null;products:Product[]}) {
  const chartMinute=minute===null?null:Math.floor(minute/60)*60;
  // Recalculate chart history only on an hour boundary or when a widget/result changes.
  const data=useMemo(()=>{
    const past=widget.series.map(point=>({date:point.date,plan:point.value??NaN,expected:point.expected??NaN,rule:NaN,dot:NaN}));
    const future=result&&day>=0?result.dates.slice(0,day+1).map((at,i)=>{
      const pointMinute=i===day?chartMinute:null;
      const plan=pointMinute===null?widgetPoint(result,widget,'scoop',products,i,null):widgetHourPoint(result,widget,'scoop',products,i,pointMinute/60);
      const rule=pointMinute===null?widgetPoint(result,widget,'baseline',products,i,null):widgetHourPoint(result,widget,'baseline',products,i,pointMinute/60);
      const lost=i===day&&pointMinute!==null?result.skus.map((_,skuIndex)=>result.runs.baseline.hourly.lost.slice(i*24,i*24+pointMinute/60).reduce((total,row)=>total+(row?.[skuIndex]||0),0)):result.runs.baseline.per_sku.lost[i];
      const dot=widget.skus.some(sku=>{const index=result.skus.indexOf(sku);return index>=0&&(lost?.[index]||0)>0});
      return {date:at,plan:plan.value??NaN,rule:rule.value??NaN,expected:plan.expected??NaN,dot:dot?rule.value??NaN:NaN};
    }):[];
    return [...past,...future];
  },[widget,result,day,chartMinute,products]);
  const hasExpected=data.some(row=>Number.isFinite(row.expected));
  const live=result&&day>=0?widgetPoint(result,widget,'scoop',products,day,minute):null;
  const value=live?live.value:widget.value;
  const state=value==null?'unknown':widget.threshold?((widget.threshold.operator==='lt'?value<widget.threshold.value:value>widget.threshold.value)?'warning':'normal'):'normal';
  const simulated=!!result&&day>=0;
  const cell=(value:number)=>Number.isFinite(value)?format(value,widget.unit):'—';
  const chart=useMemo(()=>data.some(row=>Number.isFinite(row.plan))?<Chart small data={data} percent={widget.unit==='ratio'} lines={[{key:'plan',label:simulated?'This plan':'Recorded',color:'#205a4e'},{key:'rule',label:'Moving-average rule',color:'#b28a5a'},{key:'dot',label:'Rule stockout',color:'#c96c59',dots:true},...(hasExpected?[{key:'expected',label:'Expected',color:'#8f87a6',dashed:true}]:[])]}/>:<p className="muted">No recorded history yet.</p>,[data,widget.unit,simulated,hasExpected]);
  return <><strong className="dashboard-value">{value==null?'Not available':format(value,widget.unit)}</strong>{widget.threshold&&<small className={`dashboard-current-state ${state}`}>{state==='warning'?'Alert':state==='unknown'?'Threshold unavailable':'Within threshold'}</small>}{chart}
    <details className="dashboard-evidence"><summary>Source data</summary><p className="muted">{widget.skus.length} products · {metrics.find(m=>m.id===widget.metric)?.label}{simulated?` · Simulated from ${date(result!.dates[0])}`:''}</p><div className="table-wrap"><table><thead><tr><th>Date</th><th>{simulated?'Recorded / this plan':'Recorded'}</th>{simulated&&<th>Moving-average rule</th>}{hasExpected&&<th>Expected</th>}</tr></thead><tbody>{data.map(row=><tr key={row.date}><th scope="row">{date(row.date)}</th><td>{cell(row.plan)}</td>{simulated&&<td>{cell(row.rule)}</td>}{hasExpected&&<td>{cell(row.expected)}</td>}</tr>)}</tbody></table></div></details></>;
}

function WidgetCard({widget,index,count,data,detail,result,day,minute,products,disabled,readonly,dragged,drop,move,remove,edit}:{widget:DashboardWidget;index:number;count:number;data:DashboardData;detail:Detail;result?:DashboardPlay|null;day:number;minute:number|null;products:Product[];disabled:boolean;readonly:boolean;dragged:React.RefObject<string|null>;drop:(before?:string)=>void;move:(id:string,delta:number)=>void;remove:(widget:DashboardWidget)=>void;edit:(widget:DashboardWidget)=>void}) {
  const value=result&&day>=0?widgetPoint(result,widget,'scoop',products,day,minute).value:widget.value;
  const warning=value!=null&&!!widget.threshold&&(widget.threshold.operator==='lt'?value<widget.threshold.value:value>widget.threshold.value);
  const title=widgetTitle(widget,data,detail),scopeLabel=label(widget,data);
  const scopeRepeated=title.toLocaleLowerCase().includes(scopeLabel.toLocaleLowerCase());
  const subtitle=[!scopeRepeated?scopeLabel:null,widget.threshold?`${widget.threshold.operator==='lt'?'Below':'Above'} ${format(widget.threshold.value,widget.unit)}`:null].filter(Boolean).join(' · ');
  return <article className={`dashboard-widget ${warning?'warning':''}`} draggable={!disabled} onDragStart={(e:DragEvent)=>{dragged.current=widget.id;e.dataTransfer.effectAllowed='move'}} onDragOver={e=>e.preventDefault()} onDrop={e=>{e.stopPropagation();drop(widget.id)}}><header><div><h3>{title}</h3>{subtitle&&<small>{subtitle}</small>}</div>{warning&&<span className="dashboard-warning">Alert</span>}</header><WidgetChart widget={widget} result={result} day={day} minute={minute} products={products}/>{!readonly&&<div className="dashboard-actions"><button className="text-button" disabled={disabled||index===0} aria-label={`Move ${title} up`} onClick={()=>move(widget.id,-1)}>↑</button><button className="text-button" disabled={disabled||index===count-1} aria-label={`Move ${title} down`} onClick={()=>move(widget.id,1)}>↓</button><button className="text-button" disabled={disabled} onClick={()=>edit(widget)}>Edit</button><button className="text-button" disabled={disabled} onClick={()=>remove(widget)}>Remove</button></div>}</article>;
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

export function Dashboard({detail,products,path,result,day=-1,minute=null,pending=false,readonly=false,revision=0,onChanged}:{detail:Detail;products:Product[];path:string;result?:DashboardPlay|null;day?:number;minute?:number|null;pending?:boolean;readonly?:boolean;revision?:number;onChanged?:()=>void}) {
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
  return <section className="dashboard" aria-label="Dashboard"><header className="dashboard-heading"><div><h2>Dashboard</h2>{data?.facts_through&&<small>Recorded through {date(data.facts_through)}{result&&day>=0?` · Simulated to ${date(result.dates[day])}`:''}</small>}</div>{!readonly&&<button className="button ghost" disabled={disabled} onClick={()=>setEditing(null)}><Icon name="plus" size={16}/>Add widget</button>}</header>
    {error&&<p role="alert" className="chat-error">{error}</p>}
    {!data&&!error&&<p className="muted">Loading dashboard…</p>}
    {data&&!data.widgets.length&&<p className="muted">No widgets yet. Add a measure to follow.</p>}
    <div className="dashboard-grid" onDragOver={e=>e.preventDefault()} onDrop={()=>drop()}>{data?.widgets.map((widget,index)=><WidgetCard key={widget.id} widget={widget} index={index} count={data.widgets.length} data={data} detail={detail} result={result} day={day} minute={minute} products={products} disabled={disabled} readonly={readonly} dragged={dragged} drop={drop} move={move} remove={remove} edit={setEditing}/>)}</div>
    {edit&&<EditReceipt key={edit.edit_id} edit={edit} detail={detail} path={path} onChanged={()=>{void refresh();onChanged?.()}} disabled={disabled}/>}
    {editing!==undefined&&data&&<Editor item={editing?{...editing,title:widgetTitle(editing,data,detail)}:undefined} data={data} path={path} close={()=>setEditing(undefined)} saved={changed}/>}
  </section>;
}
