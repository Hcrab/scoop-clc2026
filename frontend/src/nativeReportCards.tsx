import { renderToStaticMarkup } from 'react-dom/server';
import type { CohortCard } from './types';
import { ProductIcon } from './ProductIcon';

const signed = (value:number, digits=0) => `${value>0?'+':''}${value.toLocaleString('en-HK',{maximumFractionDigits:digits,minimumFractionDigits:digits})}`;

export function nativeCohortMarkup(card:CohortCard) {
  const direction=card.case_change>0?'+':card.case_change<0?'−':'Ⅱ';
  const evidenceId=`Q-cohort-${card.id}`;
  return renderToStaticMarkup(<div className="native-cohort-card" data-report-card="">
    <span className="native-cohort-icon" aria-hidden="true">{direction}</span>
    <div className="native-cohort-main"><h4>{card.name}</h4><p className="native-cohort-effect">{signed(card.effect_pct,1)}% estimated change</p>
      <strong className="native-cohort-cases">{signed(card.case_change)} cases</strong>
      <p className="native-cohort-impact">{signed(card.pallet_change,1)} pallets · HK${Math.round(Math.abs(card.expected_lost_margin_avoided)).toLocaleString('en-HK')} {card.expected_lost_margin_avoided<0?'extra margin lost':'lost margin avoided'}</p>
      <button type="button" data-evidence-id={evidenceId}>Open evidence</button>
    </div>
    {card.representative_sku&&<ProductIcon sku={card.representative_sku} size={96} decorative absoluteUrl/>}
  </div>);
}
