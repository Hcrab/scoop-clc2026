import type { DashboardPlay } from './Dashboard';
import type { DashboardHealth } from './types';
import { dashboardPalette as colors } from './dashboardHealth';
import { Chart } from './ui';

export const stockComparisonLines = [
  {key:'history',label:'Before the order',color:colors.history},
  {key:'plan',label:'Scoop plan',color:colors.scoop},
  {key:'rule',label:'Simple rule',color:colors.simpleRule},
];

export function resultsStockData(result:DashboardPlay, history:DashboardHealth['history'] = []) {
  const past=history.filter(point=>point.date<result.dates[0]).slice().sort((a,b)=>a.date.localeCompare(b.date)).map(point=>({
    date:point.date,history:point.on_hand_units??NaN,plan:NaN,rule:NaN,
  }));
  const anchor=[...past].reverse().find(point=>Number.isFinite(point.history));
  if(anchor){anchor.plan=anchor.history;anchor.rule=anchor.history}
  const total=(row:number[]|undefined)=>row?.reduce((sum,units)=>sum+units,0)??NaN;
  return [...past,...result.dates.map((date,day)=>({date,history:NaN,
    plan:total(result.runs.scoop.per_sku.on_hand[day]),rule:total(result.runs.baseline.per_sku.on_hand[day]),
  }))];
}

export function ResultsStockChart({result,history}:{result:DashboardPlay;history?:DashboardHealth['history']}) {
  return <div className="results-chart"><h3>Warehouse closing stock · units</h3>
    <Chart data={resultsStockData(result,history)} lines={stockComparisonLines} orderMarker={{date:result.dates[0],label:'Order placed'}}/>
  </div>;
}
