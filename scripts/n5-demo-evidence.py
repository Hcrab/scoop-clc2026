"""Reproduce the illustrative world's parameters and fitted tree evidence."""
from datetime import date
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from sqlalchemy import select

from scoop.db import SessionLocal, read_sql
from scoop.demo_config import DEMO_WEEK, QUIET_WEEK
from scoop.models import Plan
from scoop.algorithms import cohort_model
from scoop.synth.generate import build_catalog, build_demand, build_weather, _dates
from scoop.synth import compound_demo as scenario
from scoop.synth.strawberry_challenge import cells


def main():
    rng = np.random.default_rng(93)
    days = _dates()
    stores, _, products, _, _, _, tags = build_catalog(rng, seed=93)
    weather, _, _ = build_weather(rng, days, heatwave=scenario.HEATWAVE)
    baseline, _, _ = build_demand(rng, days, stores, products, tags, weather, planted=False)
    planted = baseline.copy()
    scenario.inject(planted, days, stores, products, tags)
    target, parents = cells(products, tags)
    recent = [i for i, day in enumerate(days) if date.fromisoformat(DEMO_WEEK).toordinal()-14 <= day.toordinal() < date.fromisoformat(DEMO_WEEK).toordinal()]
    effects = {}
    for name, mask in {**parents, 'intersection': np.isin(np.arange(len(products)), target)}.items():
        raw = int(baseline[recent][:, :, mask].sum())
        changed = int(planted[recent][:, :, mask].sum())
        effects[name] = dict(baseline_units=raw, planted_units=changed,
                             planted_change_pct=100 * (changed / raw - 1))
    pid = 'P' + DEMO_WEEK.replace('-', '')
    with SessionLocal() as session:
        plan = session.get(Plan, pid)
        summary = plan.summary
        plan_state = dict(id=pid, stage=plan.stage, service_level=plan.service_level)
    fitted = summary['cohort_model']
    quiet = cohort_model.fit(SimpleNamespace(week_start=date.fromisoformat(QUIET_WEEK)))
    from scoop.planning import suggest_orders, plan_cohort_cards
    quiet_orders = suggest_orders(date.fromisoformat(QUIET_WEEK), [], cohort_result=quiet)
    quiet_cards = plan_cohort_cards(date.fromisoformat(QUIET_WEEK), quiet_orders)
    result = dict(seed=93, default_week=DEMO_WEEK, quiet_week=QUIET_WEEK,
                  scenario=dict(start=scenario.START, full=scenario.FULL, end=scenario.END,
                                strawberry=scenario.STRAWBERRY_UPLIFT,
                                mango_kowloon=scenario.MANGO_KOWLOON_UPLIFT,
                                coated=scenario.COATED_CHANGE, coated_start=scenario.COATED_START,
                                coated_full=scenario.COATED_FULL,
                                heatwave={str(day): value for day, value in scenario.HEATWAVE.items()}),
                  target_skus=products.sku.iloc[target].tolist(),
                  intervention_effects=effects, plan=plan_state,
                  cards=summary.get('cohort_cards', []),
                  tested_nodes=fitted['method']['tested_nodes'], leaves=fitted['leaves'],
                  target_units=[u for u in fitted['units'] if u['sku'] in products.sku.iloc[target].tolist()],
                  quiet_cards=quiet_cards, quiet_tested_nodes=quiet['method']['tested_nodes'],
                  critical_ratios=read_sql('SELECT MIN(critical_ratio) AS min, MAX(critical_ratio) AS max FROM purchase_suggestions WHERE plan_id=:pid', pid=pid).to_dict('records'))
    path = Path('reports/n5-demo-evidence.json')
    path.write_text(json.dumps(result, default=str, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps({**{key: result[key] for key in ('target_skus', 'intervention_effects', 'tested_nodes', 'critical_ratios')},
                      'leaves': [dict(path=l['tag_path'], skus=l['skus'], effect=round(100*np.expm1(l['posterior_mean']), 2)) for l in fitted['leaves']],
                      'cards': [dict(id=c['id'], name=c['name'], effect=c['effect_pct'], skus=c['skus']) for c in result['cards']],
                      'quiet_cards': len(quiet_cards)}, indent=2))


if __name__ == '__main__':
    main()
