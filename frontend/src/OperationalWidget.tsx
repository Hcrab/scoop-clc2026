import type { DashboardHealth, DashboardWidget, Product } from './types';
import type { DashboardPlay } from './Dashboard';
import { date, n, pct } from './api';
import { widgetDisplayPoint, widgetPoint, type Policy } from './replayData';
import { dashboardPalette as colors, projectedDay } from './dashboardHealth';
import { Chart } from './ui';

export function sentenceTitle(title:string) {
  // Titles use sentence case while product codes and region acronyms retain their case.
  const acronyms=new Set(['SKU','SKUs','UK','EU','HK','HKG','NT','APAC','DC','AI']);
  let first=true;
  return title.replace(/\b[A-Za-z][A-Za-z0-9]*\b/g,word=>{
    const leading=first;first=false;
    if(acronyms.has(word)||/\d/.test(word))return word;
    const lower=word.toLowerCase();
    return leading?lower[0].toUpperCase()+lower.slice(1):lower;
  });
}
export const orderDateLabel=(value:string)=>new Date(`${value.slice(0,10)}T00:00:00Z`).toLocaleDateString('en-GB',{weekday:'short',day:'numeric',month:'short',timeZone:'UTC'});
const metricLabel=(widget:DashboardWidget)=>widget.metric==='requested_vs_expected'?'Store requests':widget.metric==='lowest_cover'?'Lowest cover':widget.metric.replaceAll('_',' ');
const format=(value:number|null|undefined,unit:DashboardWidget['unit'])=>unit==='ratio'?pct(value):unit==='days'?`${n(value,1)} ${n(value,1)==='1'?'day':'days'}`:unit==='pallets'?`${n(value,1)} pallets`:`${n(value)} units`;

export function operationalPoint(result:DashboardPlay,widget:DashboardWidget,products:Product[],health:DashboardHealth|undefined,day:number,minute:number|null,policy:Policy='scoop'):number|null {
  if(widget.metric!=='lowest_cover')return widgetPoint(result,widget,policy,products,day,minute).value;
  const values=(health?.products||[]).filter(product=>widget.skus.includes(product.sku)).map(product=>widgetPoint(result,{...widget,metric:'days_cover',skus:[product.sku],recent_demand:product.recent_demand.map((value,i)=>({date:new Date(Date.parse(`${result.dates[0]}T00:00:00Z`)-(product.recent_demand.length-i)*86400000).toISOString().slice(0,10),value}))},policy,products,day,minute).value).filter((value):value is number=>value!==null&&Number.isFinite(value));
  return values.length?Math.min(...values):null;
}

export function operationalData(widget:DashboardWidget,result:DashboardPlay|null|undefined,products:Product[],health:DashboardHealth|undefined,day:number,minute:number|null,orderDate:string,comparison=false) {
  const past=widget.series.filter(point=>point.date<orderDate).map(point=>({date:point.date,history:point.value??NaN,plan:NaN,rule:NaN}));
  const future=result&&day>=0?result.dates.slice(0,day+1).map((at,i)=>{
    const clock=i===day?minute:null;
    const point=(policy:Policy)=>clock!==null&&clock<720?NaN:operationalPoint(result,widget,products,health,i,null,policy)??NaN;
    return {date:at,history:NaN,plan:point('scoop'),rule:comparison?point('baseline'):NaN};
  }):[];
  // The boundary is shared by the two colors, never by two different measures.
  if(future.length&&!(future.length===1&&projectedDay(minute)))future[0].history=future[0].plan;
  const rows=[...past,...future];
  if(!rows.some(row=>row.date===orderDate))rows.push({date:orderDate,history:NaN,plan:NaN,rule:NaN});
  return rows.sort((a,b)=>a.date.localeCompare(b.date));
}

export function OperationalWidget({widget,result,day,minute,products,health,recordedHealth,orderDate,comparison=false}:{widget:DashboardWidget;result?:DashboardPlay|null;day:number;minute:number|null;products:Product[];health?:DashboardHealth;recordedHealth?:DashboardHealth;orderDate:string;comparison?:boolean}) {
  const active=!!result&&day>=0;
  const live=active?widget.metric==='lowest_cover'?{value:operationalPoint(result!,widget,products,recordedHealth,day,minute),yesterday:false}:widgetDisplayPoint(result!,widget,products,day,minute):null;
  const raw=live?live.value:widget.value;
  const selected=(health?.products||[]).filter(product=>widget.skus.includes(product.sku));
  const daily=selected.every(product=>product.daily_demand!==null)?selected.reduce((total,product)=>total+(product.daily_demand??0),0):0;
  const cover=widget.metric==='on_hand'&&daily>0;
  const value=cover&&raw!==null?raw/daily:raw,unit=cover?'days':widget.unit;
  const warning=raw!==null&&widget.threshold&&(widget.threshold.operator==='lt'?raw<widget.threshold.value:raw>widget.threshold.value);
  const tone=warning?colors.coral:colors.scoop;
  const note=live?.yesterday?'Yesterday':cover?`${format(raw,'units')} on hand`:null;
  const rows=operationalData(widget,result,products,recordedHealth,day,minute,orderDate,comparison);
  const planLabel=comparison?'Scoop plan':'Since the order';
  const lines=[{key:'history',label:'Before the order',color:colors.history},{key:'plan',label:planLabel,color:colors.scoop},...(comparison?[{key:'rule',label:'Simple rule',color:colors.simpleRule}]:[])];
  const cell=(value:number)=>Number.isFinite(value)?format(value,widget.unit):'—';
  return <><div className="dashboard-value"><strong style={{color:tone}}>{value===null?'—':format(value,unit)}</strong>{note&&<small>{note}</small>}</div>
    <Chart small data={rows} partialLast={active&&projectedDay(minute)} partialLabel="Projected full day" percent={widget.unit==='ratio'} orderMarker={{date:orderDate,label:'Order placed'}} lines={lines}/>
    <details className="dashboard-evidence"><summary>Source data</summary><p className="muted">{widget.skus.length} products · {metricLabel(widget)}</p><div className="table-wrap"><table><thead><tr><th>Date</th><th>Before the order</th><th>{planLabel}</th>{comparison&&<th>Simple rule</th>}</tr></thead><tbody>{rows.map(row=><tr key={row.date}><th scope="row">{date(row.date)}{active&&projectedDay(minute)&&row.date===result!.dates[day]&&minute!==null&&minute>=720?' · projected':''}</th><td>{row.date<orderDate?cell(row.history):'—'}</td><td>{cell(row.plan)}</td>{comparison&&<td>{cell(row.rule)}</td>}</tr>)}</tbody></table></div></details></>;
}
