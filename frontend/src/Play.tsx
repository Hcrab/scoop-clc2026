import { useEffect, type Dispatch, type SetStateAction } from 'react';
import { api, date, fullDate, n, pct } from './api';
import { Dashboard, type DashboardPlay } from './Dashboard';
import { Icon } from './ui';
import type { Detail, Product } from './types';

type Policy = 'scoop'|'baseline';
type Summary = {fill_rate:number;lost_units:number;lost_margin:number;avg_pallets:number;peak_pallets:number;days_over_capacity:number;stockout_sku_days:number;ending_on_hand:number;ordered_cases:number};
type PlayEvent = {date:string;kind:string;tone:'good'|'bad'|'warn'|'neutral';text:string;sku?:string;order_date?:string;cases?:number;card_ids?:string[]};
export type PlayResult = DashboardPlay & {start:string;end:string;days:number;events:PlayEvent[];summary:Record<Policy,Summary>;notes:Record<string,string|null>;affected_skus:string[];affected_summary:Record<Policy,Summary>;affected_comparison:{units_saved:number;pallet_difference:number;stockout_days_avoided:number}};
export type ReplayState = {planId:string;speed:number;result:PlayResult|null;loading:boolean;error:string;day:number;running:boolean};
export const emptyReplay=(planId=''):ReplayState=>({planId,speed:1,result:null,loading:false,error:'',day:-1,running:false});
const SPEEDS=[{label:'1×',factor:1},{label:'2×',factor:2},{label:'4×',factor:4}];
const POLICY_LABEL:Record<Policy,string>={scoop:'This plan',baseline:'Moving-average rule'};

function Comparison({result,products}:{result:PlayResult;products:Product[]}){
  const rows:[string,(x:Summary)=>string,(s:Summary,b:Summary)=>number][]=[
    ['Fill rate to stores',x=>pct(x.fill_rate),(s,b)=>s.fill_rate-b.fill_rate],
    ['Units short',x=>n(x.lost_units),(s,b)=>b.lost_units-s.lost_units],
    ['Margin lost (HKD)',x=>n(x.lost_margin),(s,b)=>b.lost_margin-s.lost_margin],
    ['Stockout product-days',x=>n(x.stockout_sku_days),(s,b)=>b.stockout_sku_days-s.stockout_sku_days],
    ['Average pallets used',x=>n(x.avg_pallets,1),(s,b)=>b.avg_pallets-s.avg_pallets],
    ['Peak pallets',x=>n(x.peak_pallets,1),(s,b)=>b.peak_pallets-s.peak_pallets],
  ];
  const table=(caption:string,summary:Record<Policy,Summary>)=><table><caption>{caption}</caption><thead><tr><th/><th>{POLICY_LABEL.scoop}</th><th>{POLICY_LABEL.baseline}</th></tr></thead><tbody>{rows.map(([name,format,compare])=>{const better=compare(summary.scoop,summary.baseline);return <tr key={name}><td>{name}</td><td className={better>1e-9?'better':better< -1e-9?'worse':''}>{format(summary.scoop)}</td><td>{format(summary.baseline)}</td></tr>})}</tbody></table>;
  const affected=result.affected_comparison;
  const names=new Map(products.map(product=>[product.sku,product.name]));
  return <section className="play-comparison"><h2>Results · {fullDate(result.start)} – {fullDate(result.end)}</h2>
    <div className="play-outcomes"><div><span>{affected.units_saved<0?'Extra units short':'Units saved'}</span><strong>{n(Math.abs(affected.units_saved))}</strong></div><div><span>Average pallet difference</span><strong>{n(affected.pallet_difference,1)}</strong></div><div><span>{affected.stockout_days_avoided<0?'Extra stockout product-days':'Stockout product-days avoided'}</span><strong>{n(Math.abs(affected.stockout_days_avoided))}</strong></div></div>
    <details><summary>Affected products · {result.affected_skus.length}</summary><ul>{result.affected_skus.map(sku=><li key={sku}>{names.get(sku)||sku}</li>)}</ul></details>
    <details><summary>See full comparison</summary>{result.affected_skus.length===result.skus.length?table(`Whole warehouse · ${result.affected_skus.length} affected products`,result.summary):<>{table('Affected products',result.affected_summary)}{table('Whole warehouse',result.summary)}</>}<p className="muted">Cold-store limit: {n(result.capacity_pallets)} pallets.</p></details>
  </section>;
}

export function PlayWeek({detail,products,path,replay,setReplay,onChanged,onReviewOrders,revision=0}:{detail:Detail;products:Product[];path:string;replay:ReplayState;setReplay:Dispatch<SetStateAction<ReplayState>>;onChanged?:()=>void;onReviewOrders?:()=>void;revision?:number}){
  const {speed,result,loading,error,day,running}=replay;
  const update=(patch:Partial<ReplayState>)=>setReplay(current=>({...current,...patch}));
  useEffect(()=>{if(replay.planId!==detail.plan.id)setReplay(emptyReplay(detail.plan.id))},[detail.plan.id,replay.planId,setReplay]);
  async function start(){update({error:''});let play=result;if(!play){update({loading:true});try{play=await api<PlayResult>(`${path}/play`,'POST',{});update({result:play,loading:false})}catch(e){update({error:(e as Error).message,loading:false});return}}setReplay(current=>({...current,day:current.day>=play!.days-1?0:Math.max(0,current.day),running:true}))}
  const complete=!!result&&day>=result.days-1&&!running;
  const today=result&&day>=0?result.dates[day]:null;
  const events=result&&today?result.events.filter(event=>event.date<=today).slice().reverse():[];
  return <section className="play"><div className="play-bar"><div className="play-clock"><span>{today?`Day ${day+1} of ${result!.days}`:'Ready'}</span><strong>{today?fullDate(today):`Week of ${fullDate(detail.plan.week_start)}`}</strong></div><div className="segmented" aria-label="Replay speed">{SPEEDS.map((item,i)=><button key={item.label} className={speed===i?'active':''} aria-pressed={speed===i} onClick={()=>update({speed:i})}>{item.label}</button>)}</div>{running?<button className="button ghost" onClick={()=>update({running:false})}>Pause</button>:<button className="button primary" disabled={loading} onClick={start}>{loading?'Preparing…':complete?'Replay':day>=0?'Resume':'Play this order through'}<Icon name="arrow" size={16}/></button>}</div>
    <p className="play-autopilot">Week-2 orders are placed automatically on both sides.</p>
    {error&&<p className="chat-error" role="alert">{error}</p>}
    <div className="play-body"><div>{complete&&result&&<Comparison result={result} products={products}/>}<Dashboard detail={detail} products={products} path={path} result={result} day={day} pending={loading||!!result&&day<result.days-1} revision={revision} onChanged={onChanged}/></div><aside className="play-events" aria-live="polite"><h3>What happened</h3>{events.length?events.map((event,i)=><div key={`${event.date}-${i}`} className={`play-event ${event.tone}`}><span>{date(event.date)}</span><p>{event.text}</p>{event.kind==='order'&&event.sku&&<button className="text-button" disabled={!complete} onClick={onReviewOrders}>Review order · {event.sku}</button>}</div>):<p className="muted">{result?'Nothing notable yet.':'Start play to see what happens.'}</p>}</aside></div>
  </section>;
}
