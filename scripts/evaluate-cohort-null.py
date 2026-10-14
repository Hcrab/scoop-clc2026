"""Read-only single-seed cohort acceptance check; does not tune the model."""
import json
from datetime import date, timedelta
from pathlib import Path
import pandas as pd

from scoop.algorithms.cohort_model import fit_observations
from scoop.algorithms.forecast import Static, DemandModel, build_features, issued_daily_weather
from scoop.algorithms.runs import TRAIN_START, _cache_dir, _load, _save, month_end
from scoop.ai.exploration_tools import _groups
from scoop.db import get_setting, session_scope
from scoop.synth.generate import null_orders


def main():
    seed = int(get_setting('seed', '93'))
    static = Static.load()
    orders, _ = null_orders(seed)
    orders['date'] = pd.to_datetime(orders.date)
    predictions = []
    for effective in pd.date_range('2026-03-01', '2026-08-01', freq='MS'):
        name = f'N{effective:%Y%m}-v1-s{seed}'
        model = _load(name)
        if model is None:
            print(f'Training null {name}', flush=True)
            model = DemandModel.train(static, TRAIN_START, effective.date()-timedelta(days=1),
                                      orders=orders, train_quantiles=False)
            model.version = name
            _save(model, name)
        days = pd.date_range(effective, month_end(effective.date()))
        features = build_features(static, days, weather=issued_daily_weather(static, days))
        predictions.append(model.predict(features, mean_only=True))
        print(f'Predicted {name}', flush=True)
    expected = pd.concat(predictions, ignore_index=True)
    expected.to_pickle(_cache_dir() / 'null-cohort-expectations.pkl')
    with session_scope() as session:
        groups = _groups(session)
    stores = dict(zip(static.stores.store_id, static.stores.district))
    skus = sorted(static.products.sku)
    rows = []
    for week in pd.date_range('2026-05-11', '2026-08-31', freq='W-MON'):
        actual = orders[orders.date.between(week-pd.Timedelta(days=70), week-pd.Timedelta(days=1))]
        result = fit_observations(week.date(), actual[['date','store_id','sku','ordered_units']].itertuples(index=False, name=None),
                                  expected, stores, skus, list(static.promos.itertuples()), groups)
        root = result['method']['tested_nodes'][0] if result['method']['tested_nodes'] else None
        row = {'week': week.date().isoformat(), 'leaves': len(result['leaves']),
               'root_p': root['p_value'] if root else None, 'units': len(result['units'])}
        rows.append(row)
        print(json.dumps(row), flush=True)
    rate = sum(r['leaves']==1 for r in rows)/len(rows)
    output = {'seed': seed, 'world': 'null_orders(planted=False)', 'forecast': 'monthly models trained on null orders',
              'weeks': rows, 'unsplit_rate': rate, 'required_rate': .95, 'passed': rate >= .95,
              'tuning': 'none'}
    target = Path('reports/cohort-null-evaluation.json')
    target.write_text(json.dumps(output, indent=2), encoding='utf-8')
    print(json.dumps({'output': str(target), 'unsplit_rate': rate, 'passed': output['passed']}), flush=True)


if __name__ == '__main__':
    main()
