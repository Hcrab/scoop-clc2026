// Names for concrete API fields in human-facing evidence views.
const labels:Record<string,string>={
  p50:'Expected sales',demand_p50:'Expected sales',
  inventory_position:'Stock on hand and on the way',position:'Stock on hand and on the way',
  protection_period:'Planning window',dc_protection_period:'Delivery-cycle forecast',
  service_point:'In-stock target',
};
export function dataLabel(key:string){return labels[key]||key.replaceAll('_',' ')}
export function labelledEvidence(value:unknown):unknown{
  if(Array.isArray(value))return value.map(labelledEvidence);
  if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).map(([key,item])=>[labels[key]||key,labelledEvidence(item)]));
  return value;
}
