"""Read-only production-path cohort fit and private post-fit seed 93 scoring."""
from __future__ import annotations

from datetime import date

import numpy as np
from sqlalchemy import select

from cohort_eval_common import save_json
from scoop.algorithms import cohort_model
from scoop.db import SessionLocal, get_setting
from scoop.models import Plan, Product, ProductTag, Store
from scoop.synth.strawberry_challenge import answer_key

WEEK = date(2026, 7, 27)
COMMAND = "$env:PYTHONPATH='backend'; $env:PYTHONUTF8='1'; $env:OMP_NUM_THREADS='1'; $env:OPENBLAS_NUM_THREADS='1'; .venv/Scripts/python.exe scripts/evaluate-cohort-planted.py"


def main():
    if get_setting('seed') != '93':
        raise RuntimeError('Active read-only database must be seed 93')
    print('Fitting seed 93 production cohort path for 2026-07-27', flush=True)
    with SessionLocal() as session:
        plan = session.scalar(select(Plan).where(Plan.week_start == WEEK))
        if plan is None:
            raise RuntimeError('Default-week plan is absent')
        result = cohort_model.fit(plan, session)
        products = list(session.scalars(select(Product).order_by(Product.sku)))
        tags = list(session.scalars(select(ProductTag)))
        stores = list(session.scalars(select(Store).order_by(Store.id)))
        import pandas as pd
        products_frame = pd.DataFrame([{'sku': p.sku, 'size_ml': p.size_ml} for p in products])
        tags_frame = pd.DataFrame([{'sku': t.sku, 'tag_id': t.tag_id, 'value_num': t.value_num} for t in tags])
        stores_frame = pd.DataFrame([{'id': s.id, 'district': s.district} for s in stores])
        key = answer_key(products_frame, tags_frame, stores_frame)
        planted = set(key['skus'])
        groups = __import__('scoop.ai.exploration_tools', fromlist=['_groups'])._groups(session)
    print(f'Fit complete: {len(result["units"])} district units and {len(result["leaves"])} leaves', flush=True)

    equivalent = []
    for leaf in result['leaves']:
        candidates = set(result['sku_factors'])
        for part in leaf['tag_path']:
            if part['id'].startswith('district:'):
                continue
            members = set(groups[part['id']].skus)
            candidates = candidates & members if part['included'] else candidates - members
        if candidates == planted and set(leaf['districts']) == set(key['districts']):
            equivalent.append({'leaf_id': leaf['id'], 'tag_path': leaf['tag_path'],
                               'skus': leaf['skus'], 'districts': leaf['districts']})

    table = []
    for sku in sorted(planted):
        parts = [u for u in result['units'] if u['sku'] == sku]
        weight = np.array([u['expected_recent'] for u in parts], dtype=float)
        raw_y = float(np.average([u['y'] for u in parts], weights=weight))
        recent_raw = sum(u['recent_A'] + sum(c['raw'] - c['cap'] for c in u['winsorised']
                    if '2026-07-13' <= c['date'] <= '2026-07-26') for u in parts)
        raw_ratio = float(recent_raw / sum(u['recent_E'] for u in parts))
        table.append({'sku': sku, 'true_multiplier_recent14': 1.8,
                      'true_multiplier_source': 'strawberry_challenge.inject; sustained peak from 2026-07-13 through recent window 2026-07-13..26',
                      'raw_recent_requested_expected_ratio': raw_ratio,
                      'raw_y_expected_recent_weighted_log_change': raw_y,
                      'f50': result['sku_factors'][sku]['f50'],
                      'district_raw_y_rows': [{k: u[k] for k in ('district', 'y', 'recent_A', 'recent_E', 'baseline_A', 'baseline_E', 'recent_days', 'baseline_days')}
                                              for u in parts]})
    payload = {'seed': 93, 'week': WEEK.isoformat(), 'command': COMMAND,
               'method': {'fit': 'cohort_model.fit(plan, session), live seed93 database read only; current plan month model rescores 70 days with historical issued weather',
                          'answer_key_use': 'offline scoring after fitting only',
                          'raw_y_aggregation': 'district raw y weighted by expected recent units; excludes promotional days and uses fit_observations winsorisation',
                          'raw_recent_ratio': 'sum untrimmed recent requested / sum recent expected across eligible districts; restored values above per-store winsor caps',
                          'baseline_contamination': 'baseline56 is 2026-05-18..2026-07-12 and includes intervention ramp 2026-07-07..12; this can attenuate log change',
                          'ramp': 'intervention starts 2026-07-06, ramps linearly to +80% on 2026-07-13 and holds'},
               'answer_key_id': key['id'], 'planted_skus': sorted(planted),
               'isolated_equivalent_tag_path': bool(equivalent), 'equivalent_leaves': equivalent,
               'leaves_with_planted_skus': [{'leaf_id': l['id'], 'tag_path': l['tag_path'],
                                             'skus': l['skus'], 'districts': l['districts']}
                                            for l in result['leaves'] if planted.intersection(l['skus'])],
               'model_version': result['method'].get('model_version'),
               'root_test': next((n for n in result['method']['tested_nodes'] if not n['path']), None),
               'tested_nodes': result['method']['tested_nodes'],
               'planted_table': table}
    save_json('reports/cohort-seed93-block-evaluation.json', payload)
    print({'isolated_equivalent_tag_path': bool(equivalent), 'planted_skus': len(table)}, flush=True)


if __name__ == '__main__':
    main()
