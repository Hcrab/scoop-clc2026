import { useEffect, useMemo, type Dispatch, type SetStateAction } from 'react';
import { date, fullDate, n, pct } from './api';
import { Dashboard, type DashboardPlay } from './Dashboard';
import { Chart } from './ui';
import { palletsFor } from './replayData';
import type { Detail, Product } from './types';
import { ProductIcon } from './ProductIcon';

type Policy = 'scoop'|'baseline';
type Summary = {fill_rate:number;lost_units:number;lost_margin:number;avg_pallets:number;peak_pallets:number;days_over_capacity:number;stockout_sku_days:number;ending_on_hand:number;ordered_cases:number};
type PlayEvent = {id:string;date:string;minute:number;time:string;at:string;kind:string;tone:'good'|'bad'|'warn'|'neutral';text:string;sku?:string;order_date?:string;cases?:number;card_ids?:string[]};
export type PlayResult = DashboardPlay & {start:string;end:string;days:number;events:PlayEvent[];summary:Record<Policy,Summary>;notes:Record<string,string|null>;affected_skus:string[]};
export type ReplayState = {planId:string;orderHash:string|null;result:PlayResult|null;day:number;minute:number;running:boolean;unlocked:boolean};
export const emptyReplay=(planId='',orderHash:string|null=null):ReplayState=>({planId,orderHash,result:null,day:-1,minute:0,running:false,unlocked:false});
const POLICY_LABEL:Record<Policy,string>={scoop:'This plan',baseline:'Moving-average rule'};

export function Results({result,detail,products,path,revision=0}:{result:PlayResult;detail:Detail;products:Product[];path:string;revision?:number}){
  const rows:[string,(x:Summary)=>string,((s:Summary,b:Summary)=>number)?][]=[
    ['Fill rate to stores',x=>pct(x.fill_rate),(s,b)=>s.fill_rate-b.fill_rate],
    ['Units short',x=>n(x.lost_units),(s,b)=>b.lost_units-s.lost_units],
    ['Margin lost (HKD)',x=>n(x.lost_margin),(s,b)=>b.lost_margin-s.lost_margin],
    ['Stockout product-days',x=>n(x.stockout_sku_days),(s,b)=>b.stockout_sku_days-s.stockout_sku_days],
    ['Average closing pallets',x=>n(x.avg_pallets,1)],
    ['Physical peak pallets',x=>n(x.peak_pallets,1)],
    ['Days over capacity',x=>n(x.days_over_capacity)],
  ];
  const summary=result.summary;
  const table=<div className="results-table-wrap"><table><caption>Whole warehouse · actual approved orders</caption><thead><tr><th/><th>{POLICY_LABEL.scoop}</th><th>{POLICY_LABEL.baseline}</th></tr></thead><tbody>{rows.map(([name,format,compare])=>{const better=compare?.(summary.scoop,summary.baseline)??0;return <tr key={name}><th scope="row">{name}</th><td className={better>1e-9?'better':better< -1e-9?'worse':''}>{format(summary.scoop)}</td><td>{format(summary.baseline)}</td></tr>})}</tbody></table></div>;
  const unitsAvoided=summary.baseline.lost_units-summary.scoop.lost_units;
  const daysAvoided=summary.baseline.stockout_sku_days-summary.scoop.stockout_sku_days;
  const marginAvoided=summary.baseline.lost_margin-summary.scoop.lost_margin;
  const names=new Map(products.map(product=>[product.sku,product.name]));
  let planShort=0,ruleShort=0;
  const comparison=result.dates.map((at,day)=>{
    planShort+=(result.runs.scoop.per_sku.lost[day]||[]).reduce((sum,lost)=>sum+lost,0);
    ruleShort+=(result.runs.baseline.per_sku.lost[day]||[]).reduce((sum,lost)=>sum+lost,0);
    return {date:at,plan:planShort,rule:ruleShort};
  });
  return <section className="results-view"><div className="play-comparison"><h2>Results · {fullDate(result.start)} – {fullDate(result.end)}</h2>
    <div className="play-outcomes"><div className={unitsAvoided<0?'result-negative':undefined}><span>{unitsAvoided<0?'Extra units short':'Units short avoided'}</span><strong>{n(Math.abs(unitsAvoided))}</strong></div><div className={daysAvoided<0?'result-negative':undefined}><span>{daysAvoided<0?'Extra stockout product-days':'Stockout product-days avoided'}</span><strong>{n(Math.abs(daysAvoided))}</strong></div><div className={marginAvoided<0?'result-negative':undefined}><span>{marginAvoided<0?'Extra margin lost':'Lost margin avoided'}</span><strong>HK${n(Math.abs(marginAvoided))}</strong></div></div>
    <p className="results-cold-store">Same cold store ({n(result.capacity_pallets)} pallets) · this plan peaks at {n(summary.scoop.peak_pallets,1)}, the rule at {n(summary.baseline.peak_pallets,1)}</p>
    <p className="results-scenario">Illustrative scenario · simulated warehouse and store outcomes.</p>
    <div className="results-chart"><h3>Cumulative units short · whole warehouse</h3><Chart data={comparison} lines={[{key:'plan',label:'This plan',color:'#205a4e'},{key:'rule',label:'Moving-average rule',color:'#b28a5a'}]}/></div>
    <details><summary>Affected products · {result.affected_skus.length}</summary><ul>{result.affected_skus.map(sku=><li key={sku}>{names.get(sku)||sku}</li>)}</ul></details>
    <details><summary>See full comparison</summary>{table}</details>
  </div><Dashboard detail={detail} products={products} path={path} result={result} day={result.days-1} readonly revision={revision}/></section>;
}

export function PlayWeek({detail,products,path,replay,setReplay,revision=0,onSeeResults}:{detail:Detail;products:Product[];path:string;replay:ReplayState;setReplay:Dispatch<SetStateAction<ReplayState>>;revision?:number;onSeeResults:()=>void}){
  const {result,day,minute,running,unlocked}=replay;
  const ready=!!result;
  useEffect(()=>{if(ready)setReplay(current=>current.day<0?{...current,day:0,minute:0,running:true}:current.day===current.result!.days-1&&current.minute===1430?current:{...current,running:true})},[ready,setReplay]);
  const complete=ready&&day===result.days-1&&minute===1430;
  const today=result&&day>=0?result.dates[day]:null;
  const eventCount=result&&today?result.events.filter(event=>event.date<today||(event.date===today&&event.minute<=minute)).length:0;
  const events=useMemo(()=>result?result.events.slice(0,eventCount).reverse():[],[result,eventCount]);
  const hhmm=`${String(Math.floor(minute/60)).padStart(2,'0')}:${String(minute%60).padStart(2,'0')}`;
  const used=result&&day>=0?palletsFor(result,products,day,minute):0;
  const usage=result?used/result.capacity_pallets:0;
  const names=useMemo(()=>new Map(products.map(product=>[product.sku,product.name])),[products]);
  const feed=useMemo(()=>events.map(event=><div key={event.id} className={`play-event ${event.tone}`}>{event.sku&&<ProductIcon sku={event.sku} size={32} decorative/>}<div><span>{date(event.date)} · {event.time}</span><p>{event.sku&&!event.text.toLowerCase().includes((names.get(event.sku)||'').toLowerCase())?<><strong>{names.get(event.sku)||event.sku}</strong> · </>:null}{event.text}</p></div></div>),[events,names]);
  const update=(patch:Partial<ReplayState>)=>setReplay(current=>({...current,...patch}));
  return <section className="play"><div className="play-bar"><div className="play-clock" data-day={today||''} data-minute={today?minute:''}><span>{today?`Day ${day+1} of ${result!.days} · 2×`:'Preparing…'}</span><strong>{today?`${date(today)} ${hhmm}`:`Week of ${fullDate(detail.plan.week_start)}`}</strong></div>{ready&&<div className={`play-capacity ${usage>1?'over-limit':''}`} aria-label={`Cold store ${used.toFixed(1)} of ${result.capacity_pallets.toFixed(1)} pallets`}><div className="play-capacity-line"><span>Cold store</span><strong>{used.toFixed(1)} <small>/ {result.capacity_pallets.toFixed(1)} pallets</small></strong></div><div className="play-capacity-track"><div style={{width:`${Math.min(100,Math.max(0,usage*100))}%`}}/></div></div>}{ready&&(running?<button className="button ghost" onClick={()=>update({running:false})}>Pause</button>:!complete?<button className="button ghost" onClick={()=>update({running:true})}>Resume</button>:<><button className="button ghost" onClick={()=>update({day:0,minute:0,running:true})}>Replay</button><button className="button primary" disabled={!unlocked} onClick={onSeeResults}>See results</button></>)}</div>
    <div className="play-body"><div><Dashboard detail={detail} products={products} path={path} result={result} day={day} minute={minute} readonly revision={revision}/></div><aside className="play-events" aria-live="polite"><h3>What happened</h3>{events.length?feed:<p className="muted">{result?'Nothing notable yet.':'Preparing the week…'}</p>}</aside></div>
  </section>;
}
