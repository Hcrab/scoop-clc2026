import type { OrderLedgerData } from './types';

const count = (value:number, digits=0) => value.toLocaleString('en-HK', {maximumFractionDigits:digits});
const signed = (value:number) => `${value < 0 ? '−' : '+'}${count(Math.abs(value))}`;

export function OrderLedger({ledger,quantityPending=false}:{ledger:OrderLedgerData;quantityPending?:boolean}) {
  const l=ledger;
  const caseChanges=!!(l.minimum_added_cases||l.capacity_removed_cases||l.case_adjustment);
  return <details className="order-ledger">
    <summary>How we got {count(l.effective_cases)} cases</summary>
    {quantityPending&&<p className="order-ledger-note" role="status">Quantity change awaiting save or refresh. This calculation shows {count(l.effective_cases)} cases.</p>}
    <dl>
      <div><dt>Expected sales over the next {l.days} days
        {l.trend&&<span className="order-ledger-note">incl. {l.trend.percent>=0?'+':'−'}{count(Math.abs(l.trend.percent),1)}% {l.trend.name} trend</span>}
      </dt><dd>{count(l.forecast_units)}</dd></div>
      <div><dt>Safety buffer for the {count(l.in_stock_target_percent,1)}% in-stock target</dt><dd>{signed(l.safety_units)}</dd></div>
      {l.rounding_units!==0&&<div><dt>Whole-unit rounding</dt><dd>{signed(l.rounding_units)}</dd></div>}
      <div><dt>Already in the cold store</dt><dd>−{count(l.stock_units)}</dd></div>
      <div><dt>Already on the way</dt><dd>−{count(l.transit_units)}</dd></div>
      {l.surplus_units>0&&<div><dt>After stock and arrivals</dt><dd>−{count(l.surplus_units)} units</dd></div>}
      <div className="order-ledger-total"><dt>{caseChanges?'Before case adjustments':'Still needed'}</dt><dd>{count(l.need_units)} units → {count(l.packed_cases)} cases<span className="order-ledger-note">{l.units_per_case} per case · rounded up</span></dd></div>
      {l.minimum_added_cases>0&&<div><dt>Rounded up to the supplier minimum</dt><dd>+{count(l.minimum_added_cases)} cases</dd></div>}
      {l.capacity_removed_cases>0&&<div><dt>Trimmed to fit the cold store</dt><dd>−{count(l.capacity_removed_cases)} cases</dd></div>}
      {l.case_adjustment!==0&&<div><dt>{l.quantity_edited?'Your quantity adjustment':'Case adjustment'}</dt><dd>{signed(l.case_adjustment)} cases</dd></div>}
      {caseChanges&&<div className="order-ledger-total"><dt>Still needed</dt><dd>{count(l.effective_cases)} cases<span className="order-ledger-note">{l.units_per_case} per case</span></dd></div>}
    </dl>
    {l.surplus_units>0&&<p className="order-ledger-note">Existing stock and arrivals exceed the forecast and buffer by {count(l.surplus_units)} units; no extra units are needed.</p>}
    {l.quantity_edited&&<p className="order-ledger-note">Your chosen quantity replaces the calculated case count.</p>}
  </details>;
}
