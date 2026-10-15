"""Read-only P6 week/card and history-capacity measurements; no parameter tuning."""
from datetime import date
from pathlib import Path
import json

from scoop.db import engine, get_setting
from scoop.planning import suggest_orders, plan_cohort_cards
from scoop.api.service import clean
from sqlalchemy import text


def main():
    if get_setting('seed') != '93':
        raise RuntimeError('Requires the existing seed93 demo')
    with engine.connect() as connection:
        history = connection.execute(text("""
          WITH shipments AS (
            SELECT date,sku,SUM(shipped_units) AS shipped FROM store_orders GROUP BY date,sku
          ), daily AS (
            SELECT n.date,SUM((n.on_hand_units+COALESCE(s.shipped,0))::float/(p.units_per_case*p.cases_per_pallet)) AS pre_ship_pallets,
                   SUM(n.on_hand_units::float/(p.units_per_case*p.cases_per_pallet)) AS closing_pallets
            FROM node_inventory n JOIN products p USING(sku) LEFT JOIN shipments s USING(date,sku)
            WHERE n.date BETWEEN '2026-07-01' AND '2026-08-31' GROUP BY n.date
          ) SELECT * FROM daily ORDER BY pre_ship_pallets DESC
        """)).mappings().all()
        capacity = connection.execute(text("SELECT capacity_pallets FROM nodes WHERE id='DC1'")).scalar_one()
    evidence = {'seed':93,'read_only':True,'capacity_before':capacity,
                'history_rule_summer2026':{'peak':dict(history[0]),'top_five':[dict(x) for x in history[:5]]},
                'weeks':[]}
    for value in ['2026-07-13','2026-07-20','2026-07-27','2026-06-22']:
        week=date.fromisoformat(value)
        orders=suggest_orders(week,[],overrides=[])
        cards=plan_cohort_cards(week,orders)
        fit=orders.attrs['cohort_model']
        item={'week':value,'case_total':int(orders.final_cases.sum()),'model':fit['method'].get('model_version'),
              'root_test':next((x for x in fit['method']['tested_nodes'] if not x['path']),None),
              'cards':[{k:c[k] for k in ['id','name','skus','effect_pct','interval_pct','case_change','pallet_change','expected_lost_margin_avoided','tag_path']} for c in cards],
              'leaves':[{'id':l['id'],'tag_path':l['tag_path'],'skus':l['skus']} for l in fit['leaves']],
              'planted_sku_factors':{sku:fit['sku_factors'].get(sku) for sku in ['IC006','IC061','IC062','IC063']}}
        evidence['weeks'].append(item)
        print(json.dumps({'week':value,'cases':item['case_total'],'cards':[(x['name'],len(x['skus']),x['case_change']) for x in item['cards']]},ensure_ascii=False),flush=True)
        Path('reports/p6-week-evaluation.json').write_text(json.dumps(clean(evidence),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(clean(evidence['history_rule_summer2026']),ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()
