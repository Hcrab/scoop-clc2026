"""Fixed-seed no-intervention acceptance using the current plan month's model."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import json

import lightgbm as lgb
import pandas as pd

from cohort_eval_common import make_world, save_json
from scoop.algorithms.cohort_model import fit_observations
from scoop.algorithms.forecast import DemandModel, PARAMS, ROUNDS, build_features, issued_daily_weather
from scoop.algorithms.runs import TRAIN_START

SEEDS = (93, 42)
WEEKS = tuple(d.date() for d in pd.date_range('2026-05-11', '2026-08-31', freq='W-MON'))
CACHE = Path('runtime/cache/cohort-null-block-v1')
COMMAND = "$env:PYTHONPATH='backend'; $env:PYTHONUTF8='1'; $env:OMP_NUM_THREADS='1'; $env:OPENBLAS_NUM_THREADS='1'; .venv/Scripts/python.exe scripts/evaluate-cohort-null.py"


def model_for(seed, world, month):
    name = f'null-s{seed}-m{month:%Y%m}-generator-v1-mean'
    path = CACHE / f'{name}.txt'
    expected_meta = {'seed': seed, 'month': month.isoformat(), 'params': PARAMS, 'rounds': ROUNDS,
                     'catalog_skus': world.skus, 'world': 'seed-local generated null world; mean-only'}
    if path.is_file():
        meta = json.loads(path.with_suffix('.json').read_text(encoding='utf-8'))
        if any(meta.get(key) != value for key, value in expected_meta.items()):
            raise ValueError(f'Cache provenance mismatch: {path}')
        model = DemandModel(month - timedelta(days=1), version=name)
        model.categories = meta['categories']
        model.models['mean'] = lgb.Booster(model_file=str(path))
        return model
    print(f'Training {name}', flush=True)
    model = DemandModel.train(world.static, TRAIN_START, month - timedelta(days=1),
                              orders=world.orders, train_quantiles=False)
    model.version = name
    CACHE.mkdir(parents=True, exist_ok=True)
    model.models['mean'].save_model(str(path))
    path.with_suffix('.json').write_text(json.dumps({**expected_meta, 'categories': model.categories}), encoding='utf-8')
    return model


def evaluate_seed(seed):
    world = make_world(seed)
    rows = []
    for week in WEEKS:
        month = date(week.year, week.month, 1)
        model = model_for(seed, world, month)
        start, end = week - timedelta(days=70), week - timedelta(days=1)
        days = pd.date_range(start, end)
        expected = model.predict(build_features(world.static, days,
                                weather=issued_daily_weather(world.static, days)), mean_only=True)
        actual = world.orders[world.orders.date.between(pd.Timestamp(start), pd.Timestamp(end))]
        result = fit_observations(week, actual[['date', 'store_id', 'sku', 'ordered_units']].itertuples(index=False, name=None),
                                  expected, world.stores, world.skus, world.promotions, world.groups)
        root = next((node for node in result['method']['tested_nodes'] if node['path'] == []), None)
        split = root is not None and root['p_value'] < .05
        recent_start = week - timedelta(days=14)
        retrains = [date(2026, m, 1) for m in range(3, 9)]
        crossed = [d.isoformat() for d in retrains if start <= d <= end]
        recent_crossed = [d.isoformat() for d in retrains if recent_start <= d <= end]
        weather = world.weather.set_index('date').tmax
        row = {'seed': seed, 'week': week.isoformat(), 'model_version': model.version,
               'root_split': split, 'root_split_tag': root['split_tag'] if split else None,
               'root_candidate_tag': root['split_tag'] if root else None,
               'root_p': root['p_value'] if root else None, 'leaves': len(result['leaves']),
               'eligible_units': len(result['units']),
               'recent14_mean_tmax': float(weather.loc[pd.Timestamp(recent_start):pd.Timestamp(end)].mean()),
               'baseline56_mean_tmax': float(weather.loc[pd.Timestamp(start):pd.Timestamp(recent_start-timedelta(days=1))].mean()),
               'window70_retrain_dates': crossed, 'window70_crosses_retrain': bool(crossed),
               'recent14_retrain_dates': recent_crossed, 'recent14_crosses_retrain': bool(recent_crossed)}
        rows.append(row)
        print(json.dumps(row), flush=True)
    return rows


def main():
    rows = [row for seed in SEEDS for row in evaluate_seed(seed)]
    count = sum(r['root_split'] for r in rows)
    output = {'method': 'seed-local generated null worlds; monthly null-trained mean model active for each plan rescored all preceding 70 days using issued daily weather, build_features, predict(mean_only=True), fit_observations',
              'command': COMMAND, 'seeds': list(SEEDS), 'weeks_per_seed': len(WEEKS),
              'denominator': len(rows), 'root_split_count': count, 'maximum_root_splits': 3,
              'passed': count <= 3, 'tuning': 'none', 'weeks': rows}
    save_json('reports/cohort-null-block-evaluation.json', output)
    print(json.dumps({'root_split_count': count, 'denominator': len(rows), 'passed': output['passed']}), flush=True)


if __name__ == '__main__':
    main()
