import type { Detail } from './types';
import { dataLabel } from './dataLabels';

export type EvidenceSource = {id:string;kind:'query'|'finding';title:string;summary:string;args?:unknown;method?:unknown;result:unknown;finding?:Detail['findings'][number]};
const titleCase=(text:string)=>dataLabel(text).replace(/\b\w/g,match=>match.toUpperCase());
const plain=(name:string)=>({catalog_groups:'Which product groups exist',query_group:'How this product group changed',query_operations:'What changed in warehouse and stores',preview_group_orders:'How proposed orders would change',cohort_card:'How this demand group was identified',cohort_observation:'How this demand group changed'} as Record<string,string>)[name]||titleCase(name);
export function evidenceSources(detail:Detail):EvidenceSource[]{
  const queries=(detail.review?.queries||[]).map((query,index)=>{
    const result=query.result as Record<string,unknown>|null;
    const count=result&&Array.isArray(result.groups)?` · ${result.groups.length} groups`:result&&Array.isArray(result.products)?` · ${result.products.length} products`:'';
    return {id:query.id||`Q${index+1}`,kind:'query' as const,title:['cohort_card','cohort_observation'].includes(query.name)&&typeof result?.name==='string'?result.name:plain(query.name)+count,summary:plain(query.name)+count,args:query.args,method:result?.method,result:query.result};
  });
  const cardSources=(detail.cohort_cards||[]).filter(card=>!queries.some(query=>query.id===`Q-cohort-${card.id}`)).map(card=>({id:`Q-cohort-${card.id}`,kind:'query' as const,title:card.name,summary:`${card.skus.length} products · ${card.effect_pct>0?'+':''}${card.effect_pct.toFixed(1)}% vs expected`,result:card,method:card.method}));
  return [...queries,...cardSources,...detail.findings.map(f=>({id:f.id,kind:'finding' as const,title:typeof f.evidence.display==='string'?f.evidence.display:f.tag_id,summary:f.district,result:{daily:f.series,checks:f.evidence.checks,related:f.evidence.related,hypotheses:f.hypotheses},method:{statistic:f.statistic,threshold:f.threshold,q_value:f.q_value},finding:f}))];
}
export function evidenceUrl(planId:string,id:string){return `/plans/${encodeURIComponent(planId)}/evidence/${encodeURIComponent(id)}`}
export function evidenceRoute(pathname=window.location.pathname){const match=pathname.match(/^\/plans\/([^/]+)\/evidence\/([^/]+)\/?$/);if(!match)return null;try{return {planId:decodeURIComponent(match[1]),id:decodeURIComponent(match[2])}}catch{return null}}

export type EvidenceSection={name:string;rows:Record<string,unknown>[]};
export function evidenceSections(result:unknown):EvidenceSection[]{
 const sections:EvidenceSection[]=[];
 const visit=(value:unknown,path:string,depth:number)=>{
   if(depth>3||!value||typeof value!=='object')return;
   if(Array.isArray(value)){if(value.length&&value.some(row=>row&&typeof row==='object'&&!Array.isArray(row))){sections.push({name:path||'Results',rows:value.map(row=>row&&typeof row==='object'&&!Array.isArray(row)?row as Record<string,unknown>:{value:row})})}return}
   for(const [key,child] of Object.entries(value))if(key!=='method'&&(Array.isArray(child)||child&&typeof child==='object'))visit(child,path?`${path} · ${titleCase(key)}`:titleCase(key),depth+1);
 };
 visit(result,'',0);
 if(!sections.length&&result&&typeof result==='object')sections.push({name:'Summary',rows:[result as Record<string,unknown>]});
 return sections;
}
