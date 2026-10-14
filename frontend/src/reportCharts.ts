import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { Chart } from './ui';
import type { Detail } from './types';

export type FigureSpec = { id:string; series:string };
type Row = Record<string,string|number>;
type SavedChart = { html:Record<string,string>; defaultRange:string; ranges:number[] };
const definitions = [
  {key:'actual',label:'Actual',color:'#205a4e'},
  {key:'expected',label:'Expected',color:'#91a398',dashed:true},
  {key:'prior',label:'Prior year',color:'#bcae96',dashed:true},
];

export function chartSeries(value:string) {
  return definitions.filter(d=>value.split(',').map(s=>s.trim()).includes(d.key)).map(d=>d.key).join(',');
}

// The model selects a source and series. All plotted coordinates are produced by
// the same Chart component used elsewhere in the app, from saved evidence only.
export function reportCharts(detail:Detail, specs:FigureSpec[]) {
  const sources = new Map<string,{rows:Row[];percent:boolean}>();
  for(const q of detail.review?.queries||[]) {
    const result=q.result as {daily?:Record<string,unknown>[]};
    if(!q.id||!Array.isArray(result?.daily))continue;
    const rows=result.daily.filter(r=>typeof r.date==='string').map(r=>{
      const row:Row={date:String(r.date)};
      const values={actual:r.requested_units??r.actual_share,expected:r.expected_units??r.expected_share,prior:r.prior_year_units??r.prior_year_requested_units};
      for(const [key,value] of Object.entries(values))if(typeof value==='number'&&Number.isFinite(value))row[key]=value;
      return row;
    });
    sources.set(q.id,{rows,percent:result.daily.some(r=>r.actual_share!=null)&&!result.daily.some(r=>r.requested_units!=null)});
  }
  for(const f of detail.findings)sources.set(f.id,{rows:f.series.map(r=>({date:r.date,actual:r.actual_share,expected:r.expected_share})),percent:true});
  const charts:Record<string,SavedChart>={};
  const requested=[...sources.keys()].map(id=>({id,series:'actual,expected,prior'})).concat(specs);
  for(const spec of requested) {
    const source=sources.get(spec.id),series=chartSeries(spec.series),key=`${spec.id}|${series}`;
    if(!source||charts[key])continue;
    const rows=[...new Map(source.rows.map(row=>[String(row.date),row])).values()].sort((a,b)=>String(a.date).localeCompare(String(b.date)));
    const lines=definitions.filter(line=>series.split(',').includes(line.key)&&rows.some(row=>typeof row[line.key]==='number'));
    const ranges=[7,14,28].filter(days=>rows.length>=days&&rows.slice(-days).every((row,i,tail)=>!i||Date.parse(String(row.date))-Date.parse(String(tail[i-1].date))===86400000));
    const html:Record<string,string>={};
    for(const range of ['all',...ranges.map(String)]) html[range]=renderToStaticMarkup(createElement(Chart,{data:range==='all'?rows:rows.slice(-Number(range)),lines,percent:source.percent}));
    charts[key]={html,ranges,defaultRange:ranges.includes(14)?'14':ranges.includes(7)?'7':'all'};
  }
  return charts;
}
