"""Apply only the authorized P6 physical capacity and default clock to seed 93.

Existing source rows, supplier timings, model parameters and usage ledger are retained.
Rebuild saved orders against that physical limit, and create the measured quiet week.
"""
from datetime import date
import json
from pathlib import Path
from sqlalchemy import select, text

from scoop.db import engine, get_setting, set_setting, session_scope
from scoop.models import Node, Plan, PurchaseSuggestion
from scoop.demo_config import DEMO_SEED, DEMO_CAPACITY_PALLETS, DEMO_WEEK, DEMO_SCENARIO, QUIET_WEEK
from scoop.demo_worlds import clear_runtime_caches
from scoop.planning import build_plan
from scoop.api.service import recompute, clean
from scoop.ai.weekly import offline_report


def source_signature():
    with engine.connect() as c:
        return dict(c.execute(text('''SELECT
            (SELECT COUNT(*) FROM store_orders) AS order_rows,
            (SELECT SUM(ordered_units) FROM store_orders) AS requested_units,
            (SELECT SUM(shipped_units) FROM store_orders) AS shipped_units,
            (SELECT SUM(on_hand_units) FROM node_inventory) AS inventory_units,
            (SELECT COUNT(*) FROM purchase_orders WHERE source='history') AS history_pos''')).mappings().one())


def main():
    assert get_setting('seed')==str(DEMO_SEED)
    before=source_signature()
    record={'seed':DEMO_SEED,'previous_clock':get_setting('today'),'source_before':before,'plans':[]}
    with session_scope() as session:
        node=session.get(Node,'DC1')
        record['capacity_before']=node.capacity_pallets
        node.capacity_pallets=DEMO_CAPACITY_PALLETS
    clear_runtime_caches()
    with session_scope() as session:
        plans=list(session.scalars(select(Plan).order_by(Plan.week_start)))
        for plan in plans:
            prior=list(session.scalars(select(PurchaseSuggestion).where(PurchaseSuggestion.plan_id==plan.id)))
            previous=sum(x.final_cases if x.final_cases is not None else x.suggested_cases-x.capacity_cut_cases for x in prior)
            recompute(session,plan)
            # Capacity evidence has changed; do not reuse the previous weekly report.
            plan.summary={**plan.summary,'weekly_review':offline_report(plan)}
            if plan.week_start.isoformat()==DEMO_WEEK: plan.stage='discover'
            session.flush()
            rows=list(session.scalars(select(PurchaseSuggestion).where(PurchaseSuggestion.plan_id==plan.id)))
            current=sum(x.final_cases if x.final_cases is not None else x.suggested_cases-x.capacity_cut_cases for x in rows)
            record['plans'].append({'id':plan.id,'before_cases':previous,'after_cases':current})
            print('Recomputed',plan.id,previous,'->',current,'cases',flush=True)
        quiet_id='P'+QUIET_WEEK.replace('-','')
        quiet_exists=session.get(Plan,quiet_id) is not None
    if not quiet_exists:
        build_plan(date.fromisoformat(QUIET_WEEK))
    set_setting('today',DEMO_WEEK)
    set_setting('demo_scenario',DEMO_SCENARIO)
    record.update(capacity_after=DEMO_CAPACITY_PALLETS,default_week=DEMO_WEEK,quiet_week=QUIET_WEEK,source_after=source_signature())
    assert record['source_after']==before
    Path('reports/p6-capacity-correction.json').write_text(json.dumps(clean(record),indent=2)+'\n',encoding='utf-8')
    print(json.dumps(clean(record)),flush=True)


if __name__=='__main__': main()
