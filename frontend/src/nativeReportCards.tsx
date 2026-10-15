import { renderToStaticMarkup } from 'react-dom/server';
import type { CohortCard } from './types';
import { ProductIcon } from './ProductIcon';

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
