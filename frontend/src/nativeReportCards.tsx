import { renderToStaticMarkup } from 'react-dom/server';
import type { CohortCard, Detail } from './types';
import { ProductIcon } from './ProductIcon';
import { productVisuals } from './productVisuals';
import { evidenceSources } from './evidence';

type EvidenceRow = Record<string, unknown>;
const record = (value:unknown):EvidenceRow => value && typeof value==='object' && !Array.isArray(value) ? value as EvidenceRow : {};
const rows = (value:unknown):EvidenceRow[] => Array.isArray(value) ? value.map(record) : [];
const strings = (value:unknown):string[] => Array.isArray(value) ? value.filter((item):item is string=>typeof item==='string') : [];
const sameMembers = (a:string[],b:string[]) => a.length===b.length && a.every(value=>b.includes(value));

// Resolve by saved evidence identity and catalog membership, never report wording.
// Cohort representatives already use greatest signed excess, then product name.
export function reportProductRepresentatives(detail:Detail) {
  const representatives = new Map<string,string>();
  const names = new Map(Object.entries(productVisuals).map(([sku,visual])=>[sku,visual.name]));
  const groups = new Map<string,string[]>();
  for(const query of detail.review?.queries||[]) {
    if(query.name!=='catalog_groups')continue;
    for(const group of rows(record(query.result).groups)) {
      if(typeof group.id==='string')groups.set(group.id,strings(group.skus));
      for(const member of rows(group.members))if(typeof member.sku==='string'&&typeof member.name==='string')names.set(member.sku,member.name);
    }
  }
  const modelUnits=rows(record(record(detail.plan.summary).cohort_model).units);
  const rank=(values:EvidenceRow[],skus:string[],districts:string[],cohortUnits=false) => {
    const totals=new Map<string,number>();
    for(const row of values) {
      if(typeof row.sku!=='string'||!skus.includes(row.sku)||!Object.hasOwn(productVisuals,row.sku))continue;
      if(cohortUnits&&districts.length&&!districts.includes(String(row.district)))continue;
      const excess=cohortUnits ? typeof row.recent_A==='number'&&typeof row.recent_E==='number'?row.recent_A-row.recent_E:null : row.excess_units;
      if(typeof excess!=='number'||!Number.isFinite(excess))continue;
      totals.set(row.sku,(totals.get(row.sku)||0)+excess);
      if(typeof row.name==='string')names.set(row.sku,row.name);
    }
    return [...totals.keys()].sort((a,b)=>(totals.get(b)!-totals.get(a)!) || (names.get(a)||a).localeCompare(names.get(b)||b) || a.localeCompare(b))[0];
  };
  const resolve=(value:unknown) => {
    const result=record(value),scope=record(result.scope),method=record(result.method);
    const skus=strings(scope.skus??result.skus),districts=strings(scope.districts??result.districts);
    if(!skus.length)return undefined;
    const card=detail.cohort_cards?.find(card=>sameMembers(card.skus,skus)&&sameMembers(card.districts,districts));
    const supplied=card?.representative_sku??result.representative_sku;
    if(typeof supplied==='string'&&skus.includes(supplied)&&Object.hasOwn(productVisuals,supplied))return supplied;
    const contributors=rows(result.sku_contributors);
    const units=rows(method.units);
    const fromModel=rank(units.length?units:modelUnits,skus,districts,true);
    if(fromModel)return fromModel;
    // Query contributors are capped by absolute excess. A positive maximum is
    // still represented; an all-negative truncated list cannot identify the
    // greatest signed excess among omitted products.
    if(contributors.length&&(contributors.length>=skus.length||contributors.some(row=>typeof row.excess_units==='number'&&row.excess_units>=0)))return rank(contributors,skus,districts);
    return undefined;
  };
  for(const source of evidenceSources(detail)) {
    let sku=resolve(source.result);
    if(!sku&&source.finding) {
      const members=groups.get(source.finding.tag_id);
      if(members)sku=resolve({skus:members,districts:[source.finding.district]});
    }
    if(sku)representatives.set(source.id,sku);
  }
  for(const trend of detail.raw_trends?.items||[]) {
    const sku=resolve(trend);
    if(sku)representatives.set(trend.id,sku);
  }
  return representatives;
}

export function decorateReportProductIcons(document:Document,detail:Detail) {
  const representatives=reportProductRepresentatives(detail);
  document.querySelectorAll<HTMLElement>('[data-report-card]').forEach(card=>{
    const trigger=card.querySelector<HTMLElement>('[data-trend-id]');
    if(!trigger)return;
    // The expand source describes the card's scope. A secondary query elsewhere
    // in the card must not override it with a broader product illustration.
    const sku=representatives.get(trigger.dataset.trendId||'');
    if(!sku)return;
    const anchor=document.createElement('span');
    anchor.className='report-trend-icon-anchor';
    const icon=document.createElement('span');
    icon.className='report-product-icon';
    icon.dataset.productSku=sku;
    icon.innerHTML=renderToStaticMarkup(<ProductIcon sku={sku} size={32} decorative absoluteUrl/>);
    trigger.before(anchor);
    anchor.append(icon,trigger);
  });
}

export function nativeCohortMarkup(card:CohortCard) {
  const label={increase:'Increase',reduce:'Reduce',hold:'Hold'}[card.action];
  const magnitude=card.action==='hold'?'keep watching':card.magnitude;
  return renderToStaticMarkup(<button type="button" className="native-cohort-action" data-direction-id={card.id} aria-label={`${label} ${card.name} · ${magnitude}`}>
    <span className={`native-cohort-direction native-cohort-direction-${card.action}`}>{label}</span>
    <ProductIcon sku={card.representative_sku} size={48} decorative absoluteUrl/>
    <span className="native-cohort-name">{card.name}</span>
    <span className="native-cohort-magnitude">· {magnitude}</span>
  </button>);
}
