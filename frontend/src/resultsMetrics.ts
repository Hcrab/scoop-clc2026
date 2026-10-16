type OutcomeSummary = {lost_units:number;stockout_sku_days:number;lost_margin:number};

export function resultsMetrics(summary:{baseline:OutcomeSummary;scoop:OutcomeSummary}) {
  return ([
    ['Units short','lost_units','fewer',false],
    ['Stockout product-days','stockout_sku_days','fewer',false],
    ['Lost margin','lost_margin','less',true],
  ] as const).map(([title,key,lowerWord,currency])=>{
    const rule=summary.baseline[key],scoop=summary.scoop[key];
    const worse=scoop>=rule;
    // A positive loss against a zero-loss rule has no finite relative percentage.
    const percent=rule===0?(scoop===0?0:null):Math.round(Math.abs(rule-scoop)/rule*100);
    return {title,rule,scoop,currency,worse,badge:percent===null?null:`${percent}% ${worse?'more':lowerWord}`};
  });
}
