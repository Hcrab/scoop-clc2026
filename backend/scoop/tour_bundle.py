"""Tour source identity and strict fixture verification; no providers are involved."""
import json
from math import isfinite
from datetime import date
from sqlalchemy.orm import Session
from . import db
from .demo_config import DEMO_WEEK, DEMO_SEED
from .demo_reset import load_initial_plan, _decode_row
from .models import Plan, PurchaseSuggestion, Setting


def source_identity(db_engine=None, schema='public'):
    """Hash pristine mechanics with SELECTs only, without locking live orders."""
    from .simulation_jobs import order_hash
    engine = db_engine or db.engine
    with engine.connect() as connection:
        with connection.begin():
            connection.exec_driver_sql('SET TRANSACTION READ ONLY')
            initial = load_initial_plan(connection, schema, DEMO_SEED, date.fromisoformat(DEMO_WEEK))
            if not initial or initial['plans'][0]['stage'] != 'discover':
                raise ValueError('Pristine default-week template is required')
            with Session(bind=connection, expire_on_commit=False) as session:
                plan_data = _decode_row(Plan.__table__, initial['plans'][0])
                plan = Plan(**plan_data)
                orders = sorted((PurchaseSuggestion(**_decode_row(PurchaseSuggestion.__table__, row))
                                 for row in initial['purchase_suggestions']), key=lambda o:o.sku)
                # Reuse the production fingerprint, substituting only its saved
                # plan/order/context inputs in memory. Physical SELECTs still
                # read the current source, so physical changes invalidate it.
                class PristineInputs:
                    def flush(self): pass
                    def scalars(self, statement):
                        class Rows:
                            def all(self): return orders
                        return Rows()
                    def get(self, model, key):
                        return None if model is Setting and key=='cohort_overrides' else session.get(model,key)
                    def execute(self, *args, **kwargs): return session.execute(*args, **kwargs)
                key = order_hash(PristineInputs(), plan)
                return {'default_week':DEMO_WEEK, 'default_order_hash':key, 'plan_id':plan.id}


def verify_bundle(bundle, source):
    if bundle.get('version') != 3:
        raise ValueError('Unsupported tour bundle version')
    for key in ('default_week','default_order_hash','plan_id'):
        if bundle.get(key) != source.get(key): raise ValueError('Stale tour bundle: '+key)
    temperature = bundle.get('meta', {}).get('heat_temp')
    if isinstance(temperature, bool) or not isinstance(temperature, (int, float)) or not isfinite(temperature):
        raise ValueError('Tour bundle requires actual heat temperature')
    from .tour_recalculation import recalculation
    for branch in bundle['branches'].values():
        expected = recalculation(bundle['base'], branch['snapshot'],
                                 bundle['meta']['strawberry_card_id'], bundle['meta']['strawberry_skus'])
        if branch.get('recalculation') != expected:
            raise ValueError('Tour recalculation metadata does not match recorded snapshots')
    for snapshot in [bundle['base'], *(b['snapshot'] for b in bundle['branches'].values())]:
        if snapshot['simulation']['status'] != 'ready' or not snapshot['simulation'].get('result'):
            raise ValueError('Tour replay is not complete')
    signatures = []
    for branch in bundle['branches'].values():
        snapshot = branch['snapshot']
        signatures.append(tuple(json.dumps(value,sort_keys=True) for value in (
            [(o['sku'],o['effective_cases']) for o in snapshot['detail']['orders']],
            snapshot['simulation']['result']['runs']['scoop'],
            snapshot['simulation']['result']['summary']['scoop'])))
    if any(len({s[index] for s in signatures}) != 3 for index in range(3)):
        raise ValueError('The three context branches must have distinct orders, replay and results')
    from .tour_worlds import multiplier, digest, historical_evidence, prove_replay
    if set(bundle['branches']) != {'unchanged','summer','growing'}:
        raise ValueError('Three named tour futures are required')
    unchanged = bundle['branches']['unchanged']['future']
    for name, branch in bundle['branches'].items():
        future = branch.get('future', {})
        if future.get('branch') != name or future.get('matched_skus') != sorted(bundle['meta']['strawberry_skus']):
            raise ValueError('Missing matched future metadata')
        if not all(future.get(key) == unchanged.get(key) and future.get(key) for key in
                   ('history_hash','outside_cohort_hash','original_demand_hash','weather_hash')):
            raise ValueError('Tour prior history or outside-cohort demand changed')
        if future.get('multipliers') != {day: str(multiplier(name,day)) for day in
                                         ('2026-07-27','2026-08-10','2026-08-11')}:
            raise ValueError('Incorrect tour future multiplier curve')
        proof = prove_replay(branch['snapshot']['simulation']['result'])
        if not all(future.get(key) == value for key,value in proof.items()):
            raise ValueError('Tour policies did not consume the recorded demand')
        if future.get('persisted_replays_cleared') is not True:
            raise ValueError('Future replay cache was not cleared')
        if future.get('baseline_context_control_hash') != digest(branch['snapshot']['simulation']['result']['runs']['baseline']):
            raise ValueError('Baseline context control does not match actual replay')
        if historical_evidence(branch['snapshot']) != historical_evidence(bundle['base']):
            raise ValueError('Historical tour observations changed')
    if unchanged.get('demand_hash') != unchanged.get('original_demand_hash') or unchanged.get('unchanged_physical_equal') is not True:
        raise ValueError('Unchanged future must reproduce original physical outcome')
    if bundle['branches']['unchanged']['snapshot']['simulation']['result'] != bundle['base']['simulation']['result']:
        raise ValueError('Unchanged replay differs from original physical outcome')
    evidence=bundle.get('question_evidence',bundle['base'])
    if historical_evidence(evidence) != historical_evidence(bundle['base']):
        raise ValueError('Question evidence history changed')
    for answer in bundle.get('questions',{}).values():
        if answer and (answer['snapshot_hash'] != digest(evidence) or
                       answer['source_order_hash'] != evidence['simulation']['order_hash']):
            raise ValueError('Question recording no longer matches original evidence')
