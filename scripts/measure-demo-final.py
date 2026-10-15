"""Measure normal policies, dated start-state capacity and actual receipt timing."""
from datetime import date, timedelta
import json
from pathlib import Path
from sqlalchemy import text

from scoop.db import engine, get_setting
from scoop.demo_config import DEMO_WEEK, DEMO_CAPACITY_PALLETS
from scoop.play import simulate
from scoop.planning import confirmation_capacity
from scoop.api.service import clean


def measure(pid, week, days=None):
    result=simulate(pid,week,days)
    return result, {k:result[k] for k in ['plan_id','start','end','days','capacity_pallets','summary','affected_comparison']}


def main():
    assert get_setting('seed')=='93'
    assert json.loads(get_setting('cohort_overrides','[]'))==[]
    start=date.fromisoformat(DEMO_WEEK)
    result,default=measure('P'+start.strftime('%Y%m%d'),start)
    _,same_period=measure('P20260727',date(2026,7,27),7)
    targets=['IC006','IC061','IC062','IC063']
    with engine.connect() as connection:
        quantities=dict(connection.execute(text('''SELECT sku,
            COALESCE(final_cases,suggested_cases-capacity_cut_cases) AS cases
            FROM purchase_suggestions WHERE plan_id=:pid'''),{'pid':result['plan_id']}).all())
        orders=connection.execute(text('''SELECT ps.sku,p.name,ps.order_date,
            COALESCE(ps.final_cases,ps.suggested_cases-ps.capacity_cut_cases) AS cases,s.lead_time_days
            FROM purchase_suggestions ps JOIN products p USING(sku) JOIN suppliers s ON s.id=p.supplier_id
            WHERE ps.plan_id=:pid AND ps.sku=ANY(:skus) ORDER BY ps.sku'''),
            {'pid':result['plan_id'],'skus':targets}).mappings().all()
    receipts=[]
    for order in orders:
        arrival=order['order_date']+timedelta(days=order['lead_time_days'])
        day=(arrival-start).days+1
        actual=result['runs']['scoop']['per_sku']['arrived'][day-1][result['skus'].index(order['sku'])] if 1<=day<=result['days'] else 0
        receipts.append({**dict(order),'arrival_date':arrival,'play_day':day,
                         'positive_order_arrives_days_2_5':order['cases']>0 and 2<=day<=5,
                         'simulated_arrived_units_on_date':actual})
    projection=confirmation_capacity(start,quantities)
    ratio=projection['projected_peak_pallets']/DEMO_CAPACITY_PALLETS
    assert .90<=ratio<=.95,ratio
    for policy in ('scoop','baseline'):
        assert default['summary'][policy]['peak_pallets']<=DEMO_CAPACITY_PALLETS+1e-8
        assert default['summary'][policy]['days_over_capacity']==0
    evidence={'seed':93,'active_overrides':[],'default':default,'start_state_projection':projection,
        'projected_peak_fraction':ratio,
        'history_rule_peak_fraction':default['summary']['baseline']['peak_pallets']/DEMO_CAPACITY_PALLETS,
        'strawberry_orders':receipts,'any_strawberry_order_days_2_5':any(r['positive_order_arrives_days_2_5'] for r in receipts),
        'P0_original':{'week':'2026-07-27','days':7,'scoop':{'lost_units':1815,'avg_pallets':53.1651,'peak_pallets':68.5983},
                       'baseline':{'lost_units':1344,'avg_pallets':55.2196,'peak_pallets':68.5983}},
        'P0_period_rerun':same_period,
        'comparison_note':'P0-period rerun shares week and horizon, but uses the new cohort ordering implementation and corrected physical capacity. Default week uses a 16-day window and is not a paired P0 comparison.'}
    Path('reports/demo-play-final.json').write_text(json.dumps(clean(evidence),indent=2)+'\n',encoding='utf-8')
    print(json.dumps(clean(evidence)),flush=True)


if __name__=='__main__': main()
