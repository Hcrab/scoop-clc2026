import type { DashboardWidget, Product } from './types';
import type { DashboardPlay } from './Dashboard';

export type Policy = 'scoop' | 'baseline';
export type SeriesPoint = { values:(number|null)[]; expected?:(number|null)[] };

// Keys may show elapsed flows after dispatch; charts show a full-day projection only from noon.
export function widgetDisplayPoint(result:DashboardPlay,widget:DashboardWidget,products:Product[],day:number,minute:number|null) {
  const flow=['demand','lost_units','requested_vs_expected','fill_rate'].includes(widget.metric);
  const slot=Math.min(144,Math.max(0,Math.floor((minute??1440)/10)));
  const yesterday=flow&&minute!==null&&minute<1430&&!(result.intraday.dispatch_cdf[slot]>0);
  if(yesterday)return {value:day>0?widgetPoint(result,widget,'scoop',products,day-1,null).value:widget.series.at(-1)?.value??widget.value,yesterday:true};
  return {...widgetPoint(result,widget,'scoop',products,day,minute),yesterday:false};
}

export function widgetChartPoint(result:DashboardPlay,widget:DashboardWidget,products:Product[],day:number,minute:number|null) {
  if(minute!==null&&minute<720)return {value:null};
  return widgetPoint(result,widget,'scoop',products,day,null);
}

const sum = (row:number[]|undefined, indexes:number[]) => indexes.reduce((total,i)=>total+(row?.[i]||0),0);
const indexesFor = (result:DashboardPlay, widget:DashboardWidget) => {
  const selected=new Set(widget.skus);
  return result.skus.flatMap((sku,i)=>selected.has(sku)?[i]:[]);
};
const expectedFor=(result:DashboardPlay, policy:Policy, indexes:number[], day:number, factor:number) => {
  const row=(result.expected||result.runs[policy].expected)?.[day];
  return row&&indexes.length&&indexes.every(i=>row[i]!=null)?indexes.reduce((total,i)=>total+(row[i] as number),0)*factor:null;
};

// All metrics use the same raw per-product quantities, so a scoped widget never starts another simulation.
export function widgetPoint(result:DashboardPlay, widget:DashboardWidget, policy:Policy, products:Product[], day:number, minute:number|null):{value:number|null;expected?:number|null} {
  const run=result.runs[policy], indexes=indexesFor(result,widget);
  const intraday=result.intraday;
  // 23:50 is the replay's closing tick: display the settled daily arrays there and in Results.
  const live=minute!==null&&minute<1430&&!!intraday;
  const slot=live?Math.min(144,Math.max(0,Math.floor(minute/10))):144;
  const demandFactor=live?intraday.demand_cdf[slot]:1;
  const dispatchFactor=live?intraday.dispatch_cdf[slot]:1;
  const demand=sum(result.demand[day],indexes)*demandFactor;
  const shipped=sum(run.per_sku.shipped[day],indexes)*dispatchFactor;
  const stock=live?indexes.reduce((total,i)=>{
    const opening=day===0?intraday.opening_on_hand[i]:run.per_sku.on_hand[day-1]?.[i]||0;
    const receipt=(minute as number)>=intraday.arrival_minutes[day]?.[i]?(run.per_sku.arrived[day]?.[i]||0):0;
    return total+opening+receipt-(run.per_sku.shipped[day]?.[i]||0)*dispatchFactor;
  },0):sum(run.per_sku.on_hand[day],indexes);
  const lost=live?indexes.reduce((total,i)=>{
    const opening=day===0?intraday.opening_on_hand[i]:run.per_sku.on_hand[day-1]?.[i]||0;
    const finalLoss=run.per_sku.lost[day]?.[i]||0;
    let greatest=0;
    for(let at=0;at<=slot;at++){
      const receipt=intraday.minutes[at]>=intraday.arrival_minutes[day]?.[i]?(run.per_sku.arrived[day]?.[i]||0):0;
      greatest=Math.max(greatest,Math.min(finalLoss,Math.max(0,(result.demand[day]?.[i]||0)*intraday.demand_cdf[at]-opening-receipt)));
    }
    return total+greatest;
  },0):sum(run.per_sku.lost[day],indexes);
  if(widget.metric==='on_hand')return {value:stock};
  if(widget.metric==='lost_units')return {value:lost};
  if(widget.metric==='demand')return {value:demand};
  if(widget.metric==='fill_rate')return {value:live&&(minute as number)<1080?null:demand?shipped/demand:null};
  if(widget.metric==='pallets')return {value:palletsFor(result,products,day,minute,policy,indexes)};
  if(widget.metric==='days_cover'){
    const history=(widget.recent_demand||[]).filter(point=>point.date<result.dates[0]).map(point=>point.value);
    const past=result.demand.slice(0,day).map(row=>sum(row,indexes));
    const recent=[...history,...past].slice(-7);
    if(recent.length!==7||recent.some(value=>value==null))return {value:null};
    const average=recent.reduce<number>((a,b)=>a+(b||0),0)/7;
    return {value:average>0?stock/average:null};
  }
  return {value:demand,expected:expectedFor(result,policy,indexes,day,demandFactor)};
}

export function palletsFor(result:DashboardPlay, products:Product[], day:number, minute:number|null, policy:Policy='scoop', only?:number[]):number {
  const footprints=new Map(products.map(p=>[p.sku,p.units_per_case*p.cases_per_pallet]));
  const indexes=only||result.skus.map((_,i)=>i);
  const run=result.runs[policy];
  const intraday=result.intraday;
  const live=minute!==null&&minute<1430&&!!intraday;
  const factor=live?intraday.dispatch_cdf[Math.min(144,Math.max(0,Math.floor(minute/10)))]:1;
  return indexes.reduce((total,i)=>{
    const units=live?(day===0?intraday.opening_on_hand[i]:run.per_sku.on_hand[day-1]?.[i]||0)+((minute as number)>=intraday.arrival_minutes[day]?.[i]?(run.per_sku.arrived[day]?.[i]||0):0)-(run.per_sku.shipped[day]?.[i]||0)*factor:run.per_sku.on_hand[day]?.[i]||0;
    return total+units/(footprints.get(result.skus[i])||Infinity);
  },0);
}
