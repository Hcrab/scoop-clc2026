"""Reconcile real saved lines and isolated policy edges without changing the DB."""
from contextlib import contextmanager
import csv
import io
from math import ceil

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from scoop.order_ledger import order_ledger, present_order, whole


def line(**changes):
    return {'sku': 'A', 'protection_days': 14, 'demand_p50': 100., 'target_units': 120.,
            'critical_ratio': .98, 'on_hand_units': 20, 'on_order_units': 4,
            'units_per_case': 12, 'moq_cases': 3, 'suggested_cases': 8,
            'capacity_cut_cases': 0, 'final_cases': None, 'adjustment': 1., **changes}


def reconciles(order, ledger):
    assert ledger['safety_units'] == whole(order['target_units'] - order['demand_p50'])
    assert (ledger['forecast_units'] + ledger['safety_units'] + ledger['rounding_units']
            - ledger['stock_units'] - ledger['transit_units']) == ledger['net_units']
    assert max(0, ledger['net_units']) == ledger['need_units']
    raw_need = max(0, order['target_units'] - order['on_hand_units'] - order['on_order_units'])
    assert ledger['packed_cases'] == ceil(raw_need / order['units_per_case'])
    assert (ledger['packed_cases'] + ledger['minimum_added_cases']
            - ledger['capacity_removed_cases'] + ledger['case_adjustment']) == ledger['effective_cases']
    expected = order['final_cases'] if order['final_cases'] is not None else max(0, order['suggested_cases'] - order['capacity_cut_cases'])
    assert ledger['effective_cases'] == expected


@pytest.mark.parametrize('target', [119.49, 119.5, 119.99, 120., 120.00001, 120.49, 120.5, 120.99])
def test_rounding_retains_real_pack_ceiling_and_real_safety(target):
    order = line(demand_p50=100.51, target_units=target)
    reconciles(order, order_ledger(order))


def test_supplier_minimum_only_when_it_actually_changed_the_order():
    order = line(target_units=30, suggested_cases=3)
    ledger = order_ledger(order)
    assert ledger['packed_cases'] == 1
    assert ledger['minimum_added_cases'] == 2
    reconciles(order, ledger)
    order = line(target_units=30, suggested_cases=2)
    assert order_ledger(order)['minimum_added_cases'] == 0


def test_capacity_cut_including_zeroed_minimum_order():
    for order in [line(capacity_cut_cases=2), line(target_units=30, suggested_cases=3, capacity_cut_cases=3)]:
        ledger = order_ledger(order)
        assert ledger['capacity_removed_cases'] == order['capacity_cut_cases']
        reconciles(order, ledger)


@pytest.mark.parametrize('capacity', [100, 0])
def test_actual_replenishment_algorithm_minimum_and_capacity_decisions(capacity):
    import numpy as np
    from scoop.algorithms.replenish import SkuInput, plan_orders
    item = SkuInput(sku='A', mean=10.01, pdays=14, price=10, cost=5,
                    units_per_case=12, cases_per_pallet=20, moq_cases=3,
                    on_hand=0, on_order=0, lead_days=7)
    actual = plan_orders([item], np.array([1.]), capacity).iloc[0].to_dict()
    # Persisted final_cases is normally null until approval or an explicit edit.
    order = {**line(), **actual, 'protection_days': actual['pdays'],
             'final_cases': None}
    ledger = order_ledger(order)
    reconciles(order, ledger)
    assert ledger['minimum_added_cases'] == 2
    assert ledger['capacity_removed_cases'] == (3 if capacity == 0 else 0)
    assert ledger['effective_cases'] == (0 if capacity == 0 else 3)


@pytest.mark.parametrize('final', [0, 1, 2, 6, 12])
def test_explicit_final_quantity_never_mislabels_old_minimum_or_capacity(final):
    order = line(target_units=30, suggested_cases=3, capacity_cut_cases=1, final_cases=final)
    ledger = order_ledger(order)
    reconciles(order, ledger)
    if final != 2:
        assert ledger['minimum_added_cases'] == ledger['capacity_removed_cases'] == 0
        assert ledger['quantity_edited']


def test_excess_stock_clamps_net_need_and_still_explains_explicit_order():
    order = line(on_hand_units=150, suggested_cases=0)
    ledger = order_ledger(order)
    assert ledger['net_units'] == -34
    assert ledger['surplus_units'] == 34
    assert ledger['need_units'] == ledger['packed_cases'] == ledger['effective_cases'] == 0
    reconciles(order, ledger)
    order['final_cases'] = 7
    ledger = order_ledger(order)
    assert ledger['case_adjustment'] == 7
    reconciles(order, ledger)


def test_trend_note_requires_matched_group_and_uses_the_product_factor():
    summary = {'cohort_model': {'leaves': [{'skus': ['A']}]},
               'cohort_cards': [{'skus': ['A'], 'name': 'Strawberry', 'effect_pct': 70}]}
    assert order_ledger(line(adjustment=1.4), summary)['trend'] == {'percent': pytest.approx(40), 'name': 'Strawberry'}
    assert order_ledger(line(adjustment=1.), summary)['trend'] is None
    assert order_ledger(line(sku='B', adjustment=1.4), summary)['trend'] is None
    assert order_ledger(line(adjustment=1.4))['trend'] is None


def test_presenter_replaces_algorithm_text_without_rewriting_input():
    order = line(reason='p50; protection period; service point; position')
    presented = present_order(order)
    assert order['reason'].startswith('p50')
    assert presented['effective_cases'] == presented['ledger']['effective_cases'] == 8
    assert all(word not in presented['reason'] for word in ['p50', 'protection period', 'service point', 'position'])


def test_all_75_real_default_api_lines_and_export_are_read_only(monkeypatch):
    from scoop.db import engine
    from scoop.api import service
    from scoop.demo_config import DEMO_WEEK

    @contextmanager
    def readonly():
        with Session(engine) as session:
            session.execute(text('SET TRANSACTION READ ONLY'))
            yield session
            session.rollback()

    monkeypatch.setattr(service, 'session_scope', readonly)
    pid = 'P' + DEMO_WEEK.replace('-', '')
    detail = service.get_plan(pid)
    assert len(detail['orders']) == 75
    assert all(order['final_cases'] is None for order in detail['orders']), 'Run against the clean default plan'
    for order in detail['orders']:
        reconciles(order, order['ledger'])
    assert any(o['ledger']['trend'] for o in detail['orders'])
    assert any(o['ledger']['trend'] is None for o in detail['orders'])
    exported = list(csv.DictReader(io.StringIO(service.export(pid).body.decode())))
    assert len(exported) == 75
    for order in exported:
        assert all(word not in order['reason'] for word in ['p50', 'protection period', 'service point', 'position'])


def test_generated_tour_ledgers_reconcile_all_75_lines_in_every_branch():
    import json
    from pathlib import Path
    bundle=json.loads((Path(__file__).resolve().parents[2]/'frontend/public/tour-bundle.json').read_text(encoding='utf8'))
    assert bundle['version']==3, 'Generate the actual integrated tour before accepting this phase'
    for snapshot in [bundle['base'],*[b['snapshot'] for b in bundle['branches'].values()]]:
        assert len(snapshot['detail']['orders'])==75
        for order in snapshot['detail']['orders']:
            reconciles(order,order['ledger'])
