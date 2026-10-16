"""Tour source identity and strict fixture verification; no providers are involved."""
import json
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
    if bundle.get('version') != 1:
        raise ValueError('Unsupported tour bundle version')
    for key in ('default_week','default_order_hash','plan_id'):
        if bundle.get(key) != source.get(key): raise ValueError('Stale tour bundle: '+key)
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
