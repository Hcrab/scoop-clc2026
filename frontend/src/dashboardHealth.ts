import type { DashboardHealth, DashboardHealthProduct, Product } from './types';
import type { DashboardPlay } from './Dashboard';
import { palletsFor, widgetPoint } from './replayData';

export const dashboardPalette = {
  requested:'#4e83b8', history:'#9aa6a0', scoop:'#205a4e', simpleRule:'#b77d36',
  amber:'#c18b2c', coral:'#c96c59', requestedProjected:'#95b5d5', safe:'#205a4e14',
} as const;
export type HealthTone = 'green'|'amber'|'coral';
export const fillTone = (rate:number):HealthTone => rate>=.98?'green':rate>=.95?'amber':'coral';
export const countTone = (count:number):HealthTone => count===0?'green':count<=3?'amber':'coral';
export const capacityTone = (pallets:number,capacity:number):HealthTone => pallets<=capacity*.95?'green':pallets<=capacity?'amber':'coral';
export const rankedCover = (products:DashboardHealthProduct[]) => products.filter(p=>p.days_cover!==null&&Number.isFinite(p.days_cover)).sort((a,b)=>a.days_cover!-b.days_cover!||a.sku.localeCompare(b.sku));
export const lowCover = (products:DashboardHealthProduct[]) => rankedCover(products).filter(p=>p.days_cover!<p.lead_time_days);
export const projectedDay = (minute:number|null) => minute!==null&&minute<1430;
export const showCurrentPoint = (minute:number|null) => minute===null||minute>=720;

export function stockEvidence(health:DashboardHealth|undefined,result:DashboardPlay,skus:string[],day:number,minute:number|null) {
  let dailyDemand=0,safeUnits=0;
  for(const p of health?.products||[]){
    if(!skus.includes(p.sku))continue;
    const i=result.skus.indexOf(p.sku);
    if(i<0)continue;
    const history=[...p.recent_demand,...result.demand.slice(0,day).map(row=>row[i]??null)].slice(-7);
    const daily=history.length===7&&history.every(v=>v!==null)?history.reduce<number>((a,b)=>a+(b||0),0)/7:0;
    let wait=p.lead_time_days;
    for(let d=day;d<result.dates.length;d++){
      const at=result.intraday.arrival_minutes[d]?.[i];
      if((result.runs.scoop.per_sku.arrived[d]?.[i]||0)>0&&(d>day||at>(minute??1440))){wait=Math.max(0,d-day+(at-(minute??1440))/1440);break}
    }
    dailyDemand+=daily;safeUnits+=daily*wait;
  }
  return {dailyDemand,safeUnits};
}

// Historical totals stay anchored to recorded facts. Replay adds only elapsed Scoop flows.
export function healthAtClock(health:DashboardHealth,result:DashboardPlay|null|undefined,products:Product[],day:number,minute:number|null):DashboardHealth {
  if(!result||day<0)return health;
  const run=result.runs.scoop, partial=projectedDay(minute), slot=Math.min(144,Math.max(0,Math.floor((minute??1440)/10)));
  const dispatch=partial?result.intraday.dispatch_cdf[slot]:1;
  const request=partial?result.intraday.demand_cdf[slot]:1;
  let requested=health.requested_units, shipped=health.shipped_units, productDays=health.stockout_sku_days;
  const stockouts=new Set(health.stockout_skus);
  for(let d=0;d<=day;d++){
    const current=d===day, factor=current&&partial?dispatch:1;
    // Before dispatch, today's flow cannot yet describe the service outcome.
    if(!current||!partial||dispatch>0){
      requested+=(result.demand[d]||[]).reduce((a,b)=>a+b,0)*(current&&partial?request:1);
      shipped+=(run.per_sku.shipped[d]||[]).reduce((a,b)=>a+b,0)*factor;
    }
    result.skus.forEach(sku=>{
      const loss=widgetPoint(result,{metric:'lost_units',skus:[sku]} as never,'scoop',products,d,current?minute:null).value||0;
      if(loss>0){stockouts.add(sku);productDays++}
    });
  }
  const currentProducts=health.products.map(product=>{
    const i=result.skus.indexOf(product.sku);
    if(i<0)return product;
    const history=[...product.recent_demand,...result.demand.slice(0,day).map(row=>row[i]??null)].slice(-7);
    const daily=history.length===7&&history.every(v=>v!==null)?history.reduce<number>((a,b)=>a+(b||0),0)/7:0;
    const stock=widgetPoint(result,{metric:'on_hand',skus:[product.sku]} as never,'scoop',products,day,minute).value||0;
    return {...product,on_hand_units:stock,daily_demand:daily,days_cover:daily>0?stock/daily:null,recent_demand:history};
  });
  let peak=health.peak_pallets;
  for(let d=0;d<=day;d++){
    if(d<day||!partial)peak=Math.max(peak,run.daily[d]?.pallets_pre_ship||0,run.daily[d]?.pallets||0);
    else for(let t=0;t<=(minute??0);t+=10)peak=Math.max(peak,palletsFor(result,products,d,t));
  }
  return {...health,through:result.dates[day],requested_units:requested,shipped_units:shipped,fill_rate:requested?shipped/requested:1,
    stockout_skus:[...stockouts],stockout_sku_days:productDays,products:currentProducts,
    pallets:palletsFor(result,products,day,minute),peak_pallets:peak,capacity_pallets:result.capacity_pallets};
}
