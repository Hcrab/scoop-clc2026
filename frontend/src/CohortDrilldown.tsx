import { useState } from 'react';
import { n } from './api';
import { Chart } from './ui';
import type { CohortDrilldownData, CohortDaily } from './types';
import './cohortDrilldown.css';

const signed=(value:number)=>`${value>0?'+':''}${n(value,1)}%`;
function roundedScale(value:number){
  if(!Number.isFinite(value)||value<=0)return 1;
  const unit=10**Math.floor(Math.log10(value));
  return ([1,2,5,10].find(step=>step*unit>=value)||10)*unit;
}
function ChangeBar({value,scale,tone}:{value:number;scale:number;tone:'group'|'rest'}){
  const width=Math.min(50,Math.abs(value)/scale*50);
  return <div className="drill-bar-line"><div className="drill-track"><span className="drill-zero"/><span className={`drill-bar ${tone}`} style={{left:`${value<0?50-width:50}%`,width:`${width}%`}}/></div><span className="drill-value">{signed(value)}</span></div>;
}
export function CohortDrilldown({data}:{data:CohortDrilldownData}){
  const [selected,setSelected]=useState(0),[days,setDays]=useState(14);
  const rows=[{label:'All products',effect:data.root.effect_pct,daily:data.root.daily,rest:null as number|null,count:null as number|null,restCount:null as number|null},...data.steps.map(step=>({label:step.label,effect:step.effect_pct,daily:step.daily,rest:step.rest_effect_pct,count:step.sku_count,restCount:step.rest_sku_count}))];
  const max=Math.max(...rows.flatMap(row=>row.rest==null?[Math.abs(row.effect)]:[Math.abs(row.effect),Math.abs(row.rest)]),0);
  const scale=roundedScale(max);
  const current=rows[Math.min(selected,rows.length-1)];
  const daily:CohortDaily[]=current.daily||[];
  return <div className="cohort-drilldown"><div className="drill-legend"><span><i className="group"/>Selected group</span><span><i className="rest"/>Rest of parent</span></div>
    <div className="drill-axis" aria-hidden="true"><span>−{n(scale,1)}%</span><span>0</span><span>+{n(scale,1)}%</span></div>
    <div className="drill-rows">{rows.map((row,index)=><button type="button" key={index} className={`drill-row ${index===selected?'selected':''}`} onClick={()=>setSelected(index)} aria-pressed={index===selected} aria-label={`${row.label}, selected group ${signed(row.effect)}${row.rest==null?'':`, rest of parent ${signed(row.rest)}`}`}>
      <span className="drill-row-title" style={{paddingLeft:`${index?Math.min(index,5)*14:0}px`}}>{row.label}{row.count!=null&&<small>{row.count} products · {row.restCount} in rest</small>}</span>
      <span className="drill-bars"><ChangeBar value={row.effect} scale={scale} tone="group"/>{row.rest!=null&&<ChangeBar value={row.rest} scale={scale} tone="rest"/>}</span>
    </button>)}</div>
    <div className="cohort-chart drill-chart"><div className="drill-chart-head"><strong>{current.label} · actual vs expected</strong><label>Time range<select value={days} onChange={event=>setDays(Number(event.target.value))}>{[7,14,28,70].map(value=><option key={value} value={value}>{value} days</option>)}</select></label></div><Chart data={daily.slice(-days).map(day=>({...day}))} lines={[{key:'requested_units',label:'Requested',color:'#205a4e'},{key:'expected_units',label:'Expected',color:'#91a398',dashed:true}]}/></div>
  </div>;
}
