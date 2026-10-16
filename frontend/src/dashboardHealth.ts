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
export const rankedCover = (products:DashboardHealthProduct[]) => products.filter(p=>p.daily_demand!==null&&Number.isFinite(p.daily_demand)&&p.daily_demand>0&&p.days_cover!==null&&Number.isFinite(p.days_cover)).sort((a,b)=>a.days_cover!-b.days_cover!||a.sku.localeCompare(b.sku));
export const lowCover = (products:DashboardHealthProduct[]) => rankedCover(products).filter(p=>p.days_until_arrival==null||p.days_cover!<p.days_until_arrival);
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

const dayNumber=(date:string)=>Date.parse(`${date}T00:00:00Z`)/86400000;
const plusDays=(date:string,days:number)=>new Date((dayNumber(date)+days)*86400000).toISOString().slice(0,10);

function arrivalsAtClock(product:DashboardHealthProduct,result:DashboardPlay,details:Product|undefined,index:number,day:number,minute:number|null) {
  const elapsedMinute=minute===null||!projectedDay(minute)?1440:minute;
  const schedule=(product.next_arrivals||[]).map(item=>({...item}));
  // Week one was already approved in Watch. Only placed week-two orders are known.
  for(let d=7;d<=day;d++){
    if(d===day&&minute!==null&&minute<840)continue;
    const cases=result.runs.scoop.per_sku.placed_cases?.[d]?.[index]||0;
    if(cases>0&&details)schedule.push({date:plusDays(result.dates[d],details.lead_time_days),units:cases*details.units_per_case});
  }
  schedule.sort((a,b)=>a.date.localeCompare(b.date));
  // Reconcile admitted inventory against the earliest outstanding promise,
  // including early/partial receipts. Deferrals do not invent an arrival date.
  for(let d=0;d<=day;d++){
    if(d===day&&minute!==null&&projectedDay(minute)&&minute<result.intraday.arrival_minutes[d]?.[index])continue;
    let delivered=result.runs.scoop.per_sku.arrived[d]?.[index]||0;
    for(const receipt of schedule){
      const used=Math.min(delivered,receipt.units);receipt.units-=used;delivered-=used;
    }
  }
  const wait=(receipt:{date:string})=>{
    const d=result.dates.indexOf(receipt.date),at=d>=0?(result.intraday.arrival_minutes[d]?.[index]??0):0;
    return dayNumber(receipt.date)-dayNumber(result.dates[day])+(at-elapsedMinute)/1440;
  };
  const pending=schedule.filter(receipt=>receipt.units>0&&wait(receipt)>0),first=pending[0];
  return {next_arrivals:pending,next_arrival_date:first?.date??null,days_until_arrival:first?wait(first):null};
}

// Replay starts a new reporting period and adds only elapsed Scoop flows.
export function healthAtClock(health:DashboardHealth,result:DashboardPlay|null|undefined,products:Product[],day:number,minute:number|null):DashboardHealth {
  if(!result||day<0)return health;
  const run=result.runs.scoop, partial=projectedDay(minute), slot=Math.min(144,Math.max(0,Math.floor((minute??1440)/10)));
  const dispatch=partial?result.intraday.dispatch_cdf[slot]:1;
  const request=partial?result.intraday.demand_cdf[slot]:1;
  let requested=0, shipped=0, productDays=0;
  const stockouts=new Set<string>();
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
    const daily=history.length===7&&history.every(v=>v!==null)?history.reduce<number>((a,b)=>a+(b||0),0)/7:null;
    const stock=widgetPoint(result,{metric:'on_hand',skus:[product.sku]} as never,'scoop',products,day,minute).value||0;
    return {...product,on_hand_units:stock,daily_demand:daily,days_cover:daily!==null&&daily>0?stock/daily:null,recent_demand:history,
      ...arrivalsAtClock(product,result,products.find(p=>p.sku===product.sku),i,day,minute)};
  });
  let peak=palletsFor(result,products,0,0);
  for(let d=0;d<=day;d++){
    if(d<day||!partial)peak=Math.max(peak,run.daily[d]?.pallets_pre_ship||0,run.daily[d]?.pallets||0);
    else for(let t=0;t<=(minute??0);t+=10)peak=Math.max(peak,palletsFor(result,products,d,t));
  }
  return {...health,period_start:result.dates[0],through:result.dates[day],requested_units:requested,shipped_units:shipped,fill_rate:requested?shipped/requested:1,
    stockout_skus:[...stockouts],stockout_sku_days:productDays,products:currentProducts,
    pallets:palletsFor(result,products,day,minute),peak_pallets:peak,capacity_pallets:result.capacity_pallets};
}
