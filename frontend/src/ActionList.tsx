import { useEffect, useState } from 'react';
import { api, date, n } from './api';
import { EditReceipt, type PlanEdit } from './EditReceipt';
import type { Detail, Order } from './types';
import './actionList.css';

type Group = {id:string;name:string;skus:string[]};
type Summary = {groups:Group[];edited_skus:string[];capacity:{capacity_pallets:number;projected_peak_pallets:number;inherited_peak_pallets:number;incremental_overcapacity_pallets:number;feasible:boolean}};
export function ActionList({detail,path,onChanged,onApproved,disabled=false}:{detail:Detail;path:string;onChanged:()=>void;onApproved:()=>void;disabled?:boolean}) {
  const [summary,setSummary]=useState<Summary|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[edit,setEdit]=useState<PlanEdit|null>(null);
  useEffect(()=>{let active=true;setError('');api<Summary>(`${path}/order-summary`).then(r=>{if(active)setSummary(r)}).catch(e=>active&&setError(e.message));return()=>{active=false}},[path,detail]);
  async function save(sku:string,value:number){
    if(disabled)return;
    if(!Number.isInteger(value)||value<0){setError('Enter a whole number of cases, zero or more.');return}
    setBusy(true);setError('');
    try{const result=await api<PlanEdit>(`${path}/orders/bulk`,'POST',{filter:{skus:[sku]},change:{type:'set_cases',value}});setEdit(result);setSummary(await api<Summary>(`${path}/order-summary`));onChanged()}
    catch(e){setError((e as Error).message)}finally{setBusy(false)}
  }
  async function approve(){if(disabled||busy)return;setBusy(true);setError('');try{await api(`${path}/approve-orders`,'POST',{});onApproved()}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
  const capacity=summary?.capacity;
  return <section className="action-list" aria-label="Order list">
    <div className="action-capacity">
      <div><span>Peak cold-store occupancy</span><strong>{capacity?`${n(capacity.projected_peak_pallets,1)} / ${n(capacity.capacity_pallets)} pallets`:'Calculating…'}</strong></div>
      {capacity&&<progress aria-label="Peak capacity used" max={capacity.capacity_pallets} value={Math.min(capacity.projected_peak_pallets,capacity.capacity_pallets)}/>}
      <button className="button primary" disabled={busy||disabled||!summary||!capacity?.feasible} onClick={approve}>{busy?'Saving…':'Approve orders'}</button>
    </div>
    {capacity&&!capacity.feasible&&<p role="status">{n(capacity.incremental_overcapacity_pallets,1)} additional pallets exceed the arrival limit.</p>}
    {capacity&&capacity.inherited_peak_pallets>capacity.capacity_pallets&&<p className="muted">Existing stock and inbound orders already peak at {n(capacity.inherited_peak_pallets,1)} pallets.</p>}
    {error&&<p role="alert" className="cohort-error">{error}</p>}
    {edit&&<EditReceipt key={edit.edit_id} edit={edit} detail={detail} path={path} onChanged={onChanged} disabled={busy||disabled}/>}
    {summary?.groups.map((group,i)=><OrderGroup key={group.id} group={group} initialOpen={i===0} orders={detail.orders.filter(o=>group.skus.includes(o.sku))} edited={new Set(summary.edited_skus)} busy={busy||disabled} save={save}/>)}
  </section>;
}

function OrderGroup({group,orders,initialOpen,edited,busy,save}:{group:Group;orders:Order[];initialOpen:boolean;edited:Set<string>;busy:boolean;save:(sku:string,value:number)=>Promise<void>}) {
  const [page,setPage]=useState(0),[open,setOpen]=useState(initialOpen);const pages=Math.max(1,Math.ceil(orders.length/20));
  const current=Math.min(page,pages-1),visible=orders.slice(current*20,(current+1)*20);
  return <details className="action-group" open={open} onToggle={e=>setOpen(e.currentTarget.open)}>
    <summary><h2>{group.name}</h2><span>{n(orders.reduce((sum,o)=>sum+o.final_cases,0))} cases · {orders.length} products</span></summary>
    <div className="table-wrap"><table><thead><tr><th>Product</th><th>Order date</th><th>Forecast units</th><th>Inventory position</th><th>Cases</th></tr></thead><tbody>{visible.map(order=><OrderRow key={order.sku} order={order} edited={edited.has(order.sku)} busy={busy} save={save}/>)}</tbody></table></div>
    {pages>1&&<nav className="action-pagination" aria-label={`${group.name} pages`}><button className="button ghost" disabled={current===0} onClick={()=>setPage(current-1)}>Previous</button><span>{current+1} / {pages}</span><button className="button ghost" disabled={current+1===pages} onClick={()=>setPage(current+1)}>Next</button></nav>}
  </details>;
}
function OrderRow({order,edited,busy,save}:{order:Order;edited:boolean;busy:boolean;save:(sku:string,value:number)=>Promise<void>}) {
  const [value,setValue]=useState(String(order.final_cases));
  useEffect(()=>setValue(String(order.final_cases)),[order.final_cases]);
  async function commit(){if(value!==''&&Number(value)!==order.final_cases)await save(order.sku,Number(value));else if(value==='')setValue(String(order.final_cases))}
  return <tr className={edited?'action-edited':''}><th scope="row"><strong>{order.name}</strong><small>{order.sku}{edited?' · Edited':''}</small><details><summary>Order evidence</summary><p>{order.reason}</p><span>Demand factor {n(order.adjustment,2)} · {order.units_per_case} units/case</span></details></th><td>{date(order.order_date)}</td><td>{n(order.demand_p50)}<small>{n(order.demand_p10)}–{n(order.demand_p90)}</small></td><td>{n(order.inventory_position)}</td><td><input aria-label={`Cases for ${order.name}`} type="number" min="0" step="1" value={value} disabled={busy} onChange={e=>setValue(e.target.value)} onBlur={commit} onKeyDown={e=>{if(e.key==='Enter')e.currentTarget.blur()}}/></td></tr>;
}
