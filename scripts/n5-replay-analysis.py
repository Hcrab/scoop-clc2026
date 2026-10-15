"""Read the persisted demo replay; never rerun or alter either policy."""
import json
from pathlib import Path

import numpy as np
from sqlalchemy import select

from scoop.db import SessionLocal
from scoop.models import SimulationRun, Product, Plan


def main():
    with SessionLocal() as session:
        run = session.scalar(select(SimulationRun).where(SimulationRun.plan_id == 'P20260727', SimulationRun.status == 'ready').order_by(SimulationRun.completed_at.desc()))
        names = dict(session.execute(select(Product.sku, Product.name)).all())
        review = (session.get(Plan, 'P20260727').summary or {}).get('weekly_review', {})
        result = run.result
    losses = {policy: np.array(result['runs'][policy]['per_sku']['lost']) for policy in ('scoop', 'baseline')}
    totals = {policy: losses[policy].sum(axis=0) for policy in losses}
    delta = totals['baseline']-totals['scoop']
    groups = []
    for index in np.argsort(delta):
        sku = result['skus'][index]
        if totals['scoop'][index] or totals['baseline'][index]:
            groups.append(dict(sku=sku, name=names[sku], units_avoided=float(delta[index]),
                               plan=float(totals['scoop'][index]), rule=float(totals['baseline'][index]),
                               plan_days=int((losses['scoop'][:, index] > 0).sum()),
                               rule_days=int((losses['baseline'][:, index] > 0).sum())))
    data = dict(summary=result['summary'], matched={k:v for k,v in result['matched'].items() if k != 'runs'},
                loss_products=groups, by_day=[dict(date=day,plan=float(losses['scoop'][index].sum()),
                    rule=float(losses['baseline'][index].sum())) for index,day in enumerate(result['dates'])],
                target_arrivals=[event for event in result['events'] if event['kind']=='arrival' and event.get('sku') in {'IC006','IC061','IC062','IC063'}],
                review_diagnostics={key:value for key,value in review.items() if key in {'status','error','repair','grounding','validation','validation_errors','model','usage','report_error','presentation_error','attempts'}},
                review_keys=list(review))
    matched_losses = np.array(result['matched']['runs']['scoop']['per_sku']['lost'])
    data['matched_loss_products'] = sorted([
        dict(sku=sku, name=names[sku], plan=float(matched_losses[:,index].sum()),
             rule=float(totals['baseline'][index]),
             units_avoided=float(totals['baseline'][index]-matched_losses[:,index].sum()),
             plan_days=int((matched_losses[:,index]>0).sum()),
             rule_days=int((losses['baseline'][:,index]>0).sum()))
        for index,sku in enumerate(result['skus'])
        if matched_losses[:,index].sum() or totals['baseline'][index]], key=lambda row:row['units_avoided'])
    Path('reports/n5-replay-analysis.json').write_text(json.dumps(data,indent=2),encoding='utf8')
    print(json.dumps({key:data[key] for key in ('matched','matched_loss_products','review_diagnostics')},indent=2))


if __name__ == '__main__':
    main()
