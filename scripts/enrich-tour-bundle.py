"""Append v2 annotations to genuine recorded responses using read-only source data.

Run .venv/Scripts/python.exe scripts/enrich-tour-bundle.py; no API, model or
provider call is needed, and neither snapshots nor accepted answers are changed.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, separators=(',', ':')).encode()).hexdigest()


def fingerprint(engine):
    from sqlalchemy import text
    with engine.connect() as connection:
        with connection.begin():
            connection.exec_driver_sql('SET TRANSACTION READ ONLY')
            names = connection.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")).scalars().all()
            return {name: connection.execute(text(f'SELECT md5(COALESCE(string_agg(row_hash,\'\' ORDER BY row_hash),\'\')) FROM (SELECT md5(row_to_json(t)::text) row_hash FROM public."{name}" t) x')).scalar() for name in names}


def preserved_payload(bundle):
    value = deepcopy(bundle)
    value.pop('version', None)
    value['meta'].pop('heat_temp', None)
    for branch in value['branches'].values():
        branch.pop('recalculation', None)
    return value


def enrich(path, report_path):
    from scoop import db
    from scoop.tour_bundle import source_identity, verify_bundle
    from scoop.tour_recalculation import enrich_bundle, factor_inputs, heat_temperature
    bundle = json.loads(path.read_text(encoding='utf-8'))
    original = preserved_payload(bundle)
    before = fingerprint(db.engine)
    source = source_identity()
    temperature = heat_temperature(db.engine, bundle['meta']['heat_date'])
    enrich_bundle(bundle, temperature)
    verify_bundle(bundle, source)
    assert preserved_payload(bundle) == original, 'Existing recorded payload changed'
    after = fingerprint(db.engine)
    assert before == after, 'Public database changed during enrichment'
    snapshots = {'base': bundle['base'], **{k: b['snapshot'] for k, b in bundle['branches'].items()}}
    answers = {**bundle['questions'], **{k: b['answer'] for k, b in bundle['branches'].items()}}
    report = {
        'status': 'complete', 'version': 2, 'source': source,
        'public_before': before, 'public_after': after, 'public_unchanged': True,
        'provider_calls': 0, 'database_writes': 0,
        'preserved_payload_before_sha256': digest(original),
        'preserved_payload_after_sha256': digest(preserved_payload(bundle)),
        'snapshot_hashes': {k: digest(s) for k, s in snapshots.items()},
        'answer_hashes': {k: digest(a) for k, a in answers.items()},
        'factor_definition': 'Arithmetic mean of actual plan.summary.cohort_model.sku_factors[sku].f50, weighted by the sum of expected_recent across units with the strawberry cohort leaf_id and that SKU.',
        'factor_inputs': {k: factor_inputs(s, bundle['meta']['strawberry_card_id'], bundle['meta']['strawberry_skus']) for k, s in snapshots.items()},
        'peak_source': 'snapshot.order_summary.capacity.projected_peak_pallets (planning projection, not replay physical peak)',
        'trim_definition': 'Sum of positive branch capacity_cut_cases minus clean snapshot capacity_cut_cases, by SKU; demand-driven case changes are not capacity cuts.',
        'heat': {'source': 'WeatherDaily.tmax', 'date': bundle['meta']['heat_date'], 'tmax': temperature, 'use': 'offline replay event metadata only'},
        'branches': {k: b['recalculation'] for k, b in bundle['branches'].items()},
        'incomplete': [],
    }
    path.write_text(json.dumps(bundle, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n', encoding='utf-8')
    report['bundle_sha256'] = digest(bundle)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'heat': report['heat'], 'branches': report['branches'], 'public_unchanged': True}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, default=ROOT / 'frontend/public/tour-bundle.json')
    parser.add_argument('--report', type=Path, default=ROOT / 'reports/tour2/data.json')
    args = parser.parse_args()
    enrich(args.bundle.resolve(), args.report.resolve())
