"""Offline assistant commands save scoped edits through the shared tools and undo."""
from datetime import date

import pandas as pd
from test_api_state import api
from scoop.ai import exploration_tools
from scoop.algorithms.groups import Group
from scoop.api.cohorts import order_snapshot
from scoop.cohort_context import load_overrides
from scoop.models import Plan, Product, PurchaseSuggestion


def _chat(client, message):
    response = client.post('/api/plans/TESTAPI/chat', json={'message': message, 'stage': 'discover'})
    assert response.status_code == 200, response.text
    return response.json()


def _undo(client, edit_id):
    reply = _chat(client, f'Undo edit {edit_id}')
    assert reply['actions'][0]['type'] == 'undo', reply


def test_strawberry_end_date_resolves_catalog_group_without_exact_leaf(api, monkeypatch):
    client, scope, _, planning = api
    with scope() as session:
        strawberry = session.get(Product, 'IC001')
        strawberry.name = 'Strawberry Ice Bar'
        session.add(Product(sku='IC002', name='Plain Water Bar', brand='Fixture', format='stick',
            size_ml=100, units_per_case=10, cases_per_pallet=10, price_hkd=20, cost_hkd=10,
            supplier_id='SUP', moq_cases=3, launch_date=date(2023, 1, 1), status='active', description='Fixture'))
        session.add(PurchaseSuggestion(plan_id='TESTAPI', sku='IC002', order_date=date(2026, 7, 6),
            protection_days=10, demand_p10=20, demand_p50=30, demand_p90=40, adjustment=1,
            critical_ratio=.8, target_units=40, on_hand_units=10, on_order_units=0,
            inventory_position=10, suggested_cases=3, capacity_cut_cases=0,
            status='suggested', reason='Fixture'))
        plan = session.get(Plan, 'TESTAPI')
        # The only leaf is broad; applying its scope would also change IC002.
        leaf = {'id': 'WATER-LEAF', 'name': 'Water based',
                'tag_path': [{'id': 'family:water', 'included': True}],
                'districts': [], 'skus': ['IC001', 'IC002']}
        plan.summary = {'cohort_cards': [leaf], 'cohort_model': {'leaves': [leaf], 'sku_factors': {}}}

    monkeypatch.setattr(exploration_tools, '_groups', lambda _: {
        'family:strawberry': Group('family:strawberry', 'Strawberry', 'family', ('IC001',)),
        'family:water': Group('family:water', 'Water based', 'family', ('IC001', 'IC002'))})

    def orders(as_of, directions, **kwargs):
        overrides = kwargs.get('overrides', [])
        ended = any(x['type'] == 'ends_on' and x['tag_path'] ==
                    [{'id': 'family:strawberry', 'included': True}] for x in overrides)
        frame = pd.DataFrame([{'sku': sku, 'order_date': as_of, 'pdays': 10,
            'demand_p10': 20., 'demand_p50': 30., 'demand_p90': 40., 'adjustment': 1.,
            'critical_ratio': .8, 'target_units': 40., 'on_hand_units': 10, 'on_order_units': 0,
            'inventory_position': 10, 'suggested_cases': 2 if ended and sku == 'IC001' else 3,
            'capacity_cut_cases': 0} for sku in ('IC001', 'IC002')])
        frame.attrs['cohort_model'] = {'leaves': [], 'sku_factors': {}}
        return frame

    monkeypatch.setattr(planning, 'suggest_orders', orders)
    saved = _chat(client, 'the strawberry thing is a summer one-off, it ends 10 Aug')
    action = saved['actions'][0]
    assert action['type'] == 'edit', saved
    with scope() as session:
        overrides = load_overrides(session)
        assert len(overrides) == 1
        assert overrides[0]['tag_path'] == [{'id': 'family:strawberry', 'included': True}]
        assert overrides[0]['districts'] == []
        assert overrides[0]['type'] == 'ends_on' and overrides[0]['value'] == '2026-08-10'
        assert {r['sku']: r['suggested_cases'] for r in order_snapshot(session, session.get(Plan, 'TESTAPI'))} == {
            'IC001': 2, 'IC002': 3}
    _undo(client, action['edit_id'])
    with scope() as session:
        assert load_overrides(session) == []
        assert {r['sku']: r['suggested_cases'] for r in order_snapshot(session, session.get(Plan, 'TESTAPI'))} == {
            'IC001': 3, 'IC002': 3}


def test_signed_unicode_minus_price_order_edit_and_undo(api, monkeypatch):
    client, scope, _, _ = api
    with scope() as session:
        session.get(PurchaseSuggestion, ('TESTAPI', 'IC001')).suggested_cases = 10
    monkeypatch.setattr(exploration_tools, '_groups', lambda _: {
        'band:price_hkd:0': Group('band:price_hkd:0', 'Value price', 'price_hkd', ('IC001',)),
        'band:price_100ml:0': Group('band:price_100ml:0', 'Lower price / 100 ml',
                                    'price_100ml', ('IC001',))})
    saved = _chat(client, 'All value-price lines −10%')
    action = saved['actions'][0]
    assert action['type'] == 'edit' and action['change'] == {'type': 'percent', 'value': -10.0}
    assert action['filter']['group'] == 'band:price_hkd:0'
    assert action['affected_orders'][0]['before'] == 10
    assert action['affected_orders'][0]['after'] == 9
    with scope() as session:
        assert load_overrides(session)[0]['value'] == {'sku': 'IC001', 'cases': 9}
        assert order_snapshot(session, session.get(Plan, 'TESTAPI'))[0]['final_cases'] == 9
    _undo(client, action['edit_id'])
    with scope() as session:
        assert load_overrides(session) == []
        assert order_snapshot(session, session.get(Plan, 'TESTAPI'))[0]['suggested_cases'] == 10


def test_order_percent_does_not_match_numeric_band_ids_without_a_named_scope(api,monkeypatch):
    client,scope,_,_=api
    monkeypatch.setattr(exploration_tools,'_groups',lambda _: {
        'band:price_hkd:0':Group('band:price_hkd:0','Value price','price_hkd',('IC001',)),
        'band:price_100ml:1':Group('band:price_100ml:1','Mid price / 100 ml','price_100ml',('IC001',))})
    with scope() as session:before=order_snapshot(session,session.get(Plan,'TESTAPI'))
    result=_chat(client,'All lines −10%')
    assert result['actions']==[]
    with scope() as session:assert order_snapshot(session,session.get(Plan,'TESTAPI'))==before


def test_peak_limit_routes_to_capacity_fit_and_undo(api, monkeypatch):
    client, scope, _, planning = api
    def orders(as_of, directions, **kwargs):
        fitted = kwargs.get('capacity_limit') is not None
        count = 2 if fitted else next((x['value']['cases'] for x in kwargs.get('overrides', [])
                                      if x['type'] == 'cases'), 3)
        frame = pd.DataFrame([{'sku': 'IC001', 'order_date': as_of, 'pdays': 10,
            'demand_p10': 20., 'demand_p50': 30., 'demand_p90': 40., 'adjustment': 1.,
            'critical_ratio': .8, 'target_units': 40., 'on_hand_units': 10, 'on_order_units': 0,
            'inventory_position': 10, 'suggested_cases': 3, 'capacity_cut_cases': 0,
            'final_cases': count}])
        frame.attrs['cohort_model'] = {'leaves': [], 'sku_factors': {},
            'cases_overrides': {'IC001': count} if not fitted and kwargs.get('overrides') else {}}
        return frame
    monkeypatch.setattr(planning, 'suggest_orders', orders)
    saved = _chat(client, 'keep peak below 90%')
    action = saved['actions'][0]
    assert action['type'] == 'edit' and action['change'] == {'type': 'fit_capacity', 'value': .9}
    assert action['capacity']['target_fraction'] == .9
    assert action['affected_orders'][0]['before'] == 3 and action['affected_orders'][0]['after'] == 2
    with scope() as session:
        assert order_snapshot(session, session.get(Plan, 'TESTAPI'))[0]['final_cases'] == 2
        assert load_overrides(session)[0]['value'] == {'sku': 'IC001', 'cases': 2}
    _undo(client, action['edit_id'])
    with scope() as session:
        assert load_overrides(session) == []
        assert order_snapshot(session, session.get(Plan, 'TESTAPI'))[0]['final_cases'] is None
