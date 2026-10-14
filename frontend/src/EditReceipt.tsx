import { useState } from 'react';
import { api, n } from './api';
import type { Detail } from './types';

export type PlanEdit = { edit_id?:number; label?:string; undone?:boolean; affected_orders:{sku:string;before:number;after:number;factor_before?:number;factor_after?:number}[] };

export function EditReceipt({edit,detail,path,onChanged,disabled=false}:{edit:PlanEdit;detail:Detail;path:string;onChanged:()=>void;disabled?:boolean}) {
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[undone,setUndone]=useState(false);
  const rows=edit.affected_orders||[];
  const delta=rows.reduce((sum,row)=>sum+row.after-row.before,0);
  const recorded=detail.decisions.find(d=>Number(d.id)===edit.edit_id);
  const restored=undone||edit.undone||Boolean((recorded?.value as {undone_at?:string})?.undone_at);
  async function undo(){setBusy(true);setError('');try{await api(`${path}/edits/${edit.edit_id}/undo`,'POST',{});setUndone(true);onChanged()}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
  return <div className="edit-receipt" data-edit-id={edit.edit_id}>
    <div className="edit-receipt-heading" role="status"><strong>{restored?'Change undone':rows.length?`${edit.label||'Plan updated'}: ${delta>0?'+':''}${n(delta)} cases`:edit.label||'Plan updated'}</strong>{!restored&&edit.edit_id!=null&&<button type="button" className="text-button" disabled={disabled||busy} onClick={undo}>{busy?'Undoing…':'Undo'}</button>}</div>
    {rows.length>0&&<details><summary>{n(rows.length)} products changed</summary><div className="edit-receipt-table"><table><thead><tr><th>Product</th><th>Before</th><th>After</th><th>Demand factor</th></tr></thead><tbody>{rows.map(row=><tr key={row.sku}><th scope="row">{detail.orders.find(o=>o.sku===row.sku)?.name||row.sku}</th><td>{n(row.before)}</td><td>{n(row.after)}</td><td>{row.factor_before!=null&&row.factor_after!=null?`${n(row.factor_before,2)} → ${n(row.factor_after,2)}`:'—'}</td></tr>)}</tbody></table></div></details>}
    {error&&<p role="alert" className="cohort-error">{error}</p>}
  </div>;
}
