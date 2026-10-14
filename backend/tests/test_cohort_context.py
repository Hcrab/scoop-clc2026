from datetime import date, datetime
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
import pytest
from test_api_state import api
from scoop.cohort_context import put_override, load_overrides, validate_override
from scoop.models import Setting, Plan, Decision
from scoop.algorithms.groups import Group


def test_definitions_persist_and_same_rule_updates_in_place():
    engine = create_engine('sqlite://')
    Setting.__table__.create(engine)
    with Session(engine) as session:
        body = {'tag_path': [{'id':'tag:a','included':True}], 'districts':['north'],
                'type':'cap','value':.3,'expires_on':'2026-08-10'}
        _, _, first = put_override(session, body)
        session.commit()
        _, current, second = put_override(session, {**body, 'value':.2})
        session.commit()
        assert first['id'] == second['id'] and len(current) == 1
        assert load_overrides(session, date(2026,8,3))[0]['value'] == .2
        assert load_overrides(session, date(2026,8,11)) == []
    engine.dispose()


@pytest.mark.parametrize('body', [
    {'type':'cap','value':-1}, {'type':'cap','value':float('nan')},
    {'type':'cases','value':{'sku':'A','cases':1.5}},
    {'type':'expect','value':{'pct':.2,'strength':'max'}}])
def test_context_values_have_semantic_validation(body):
    with pytest.raises(ValueError):
        validate_override(body)


def test_context_api_passes_saved_definition_into_recompute_and_returns_diff(api, monkeypatch):
    client, scope, clock, planning = api
    from scoop.ai import exploration_tools
    monkeypatch.setattr(exploration_tools, '_groups', lambda _: {'tag:a':Group('tag:a','A','kind',('IC001',))})
    seen = []
    def orders(as_of, directions, **kwargs):
        seen.append(kwargs['overrides'])
        frame = pd.DataFrame([{'sku':'IC001','order_date':as_of,'pdays':10,
            'demand_p10':20.,'demand_p50':30.,'demand_p90':40.,'adjustment':1.,
            'critical_ratio':.8,'target_units':40.,'on_hand_units':10,'on_order_units':0,
            'inventory_position':10,'suggested_cases':2,'capacity_cut_cases':0,'final_cases':2}])
        frame.attrs['cohort_model'] = {'leaves': [], 'sku_factors': {'IC001':{'f50':1.}}}
        return frame
    monkeypatch.setattr(planning, 'suggest_orders', orders)
    response = client.post('/api/plans/TESTAPI/overrides', json={
        'tag_path':[{'id':'tag:a','included':True}], 'districts':['Kowloon'],
        'type':'ends_on','value':'2026-08-10','note':'Seasonal order'})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['affected_orders'][0]['before'] == 3
    assert data['affected_orders'][0]['after'] == 2
    assert seen[0][0]['tag_path'] == [{'id':'tag:a','included':True}]
    with scope() as session:
        session.add(Plan(id='NEXT',week_start=date(2026,7,13),stage='discover',goal='margin',created_at=datetime.now(),summary={}))
    assert client.get('/api/plans/NEXT/overrides').json()[0]['value'] == '2026-08-10'
    with scope() as session:
        assert session.get(Plan,'TESTAPI').summary['cohort_model']['sku_factors']['IC001']['f50'] == 1.

    restored = client.post(f"/api/plans/TESTAPI/edits/{data['edit_id']}/undo")
    assert restored.status_code == 200, restored.text
    from scoop.api.cohorts import order_snapshot
    from scoop.models import WatchItem
    from scoop.api import service
    with scope() as session:
        plan = session.get(Plan,'TESTAPI')
        assert order_snapshot(session,plan) == data['before']['orders']
        assert plan.summary == data['before']['summary']
        assert [service.row(x) for x in service.objects(session,WatchItem,plan.id)] == data['before']['watches']
        assert load_overrides(session) == data['before']['overrides']
    assert client.post(f"/api/plans/TESTAPI/edits/{data['edit_id']}/undo").status_code == 200
