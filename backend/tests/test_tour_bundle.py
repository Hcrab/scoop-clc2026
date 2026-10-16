"""Tour source is read-only; fixtures reject stale or physically identical branches."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text, event
from scoop import db
from scoop.api.tour import router
from scoop.tour_bundle import source_identity, verify_bundle


def fixture_bundle():
    source={'default_week':'2026-07-27','default_order_hash':'original','plan_id':'P20260727'}
    def snapshot(n):
        return {'detail':{'orders':[{'sku':'A','effective_cases':n}]},
                'simulation':{'status':'ready','result':{'runs':{'scoop':{'actual':n}},'summary':{'scoop':{'lost_units':n}}}}}
    return {'version':1,**source,'base':snapshot(1),'branches':{k:{'snapshot':snapshot(n)} for n,k in enumerate(['unchanged','summer','growing'],1)}},source


def test_stale_hash_rejected():
    bundle,source=fixture_bundle()
    verify_bundle(bundle,source)
    with pytest.raises(ValueError,match='Stale tour bundle'):
        verify_bundle(bundle,{**source,'default_order_hash':'changed'})


def test_each_physical_component_must_differ():
    for component in ('orders','replay','results'):
        bundle,source=fixture_bundle()
        a=bundle['branches']['unchanged']['snapshot'];b=bundle['branches']['summer']['snapshot']
        if component=='orders':b['detail']=deepcopy(a['detail'])
        elif component=='replay':b['simulation']['result']['runs']=deepcopy(a['simulation']['result']['runs'])
        else:b['simulation']['result']['summary']=deepcopy(a['simulation']['result']['summary'])
        with pytest.raises(ValueError,match='distinct orders'):
            verify_bundle(bundle,source)


def _fingerprint():
    with db.engine.connect() as c:
        return [c.execute(text(f'SELECT md5(COALESCE(string_agg(v,\'\' ORDER BY v),\'\')) FROM (SELECT row_to_json(t)::text v FROM public.{name} t) x')).scalar() for name in ('plans','purchase_suggestions','settings','decisions','simulation_runs','purchase_orders')]


def test_source_endpoint_is_read_only(monkeypatch):
    import scoop.simulation_jobs as jobs
    from scoop.ai import gemini
    monkeypatch.setattr(gemini,'_wire',lambda *a,**k:pytest.fail('Source endpoint called provider'))
    monkeypatch.setattr(jobs,'enqueue',lambda *a,**k:pytest.fail('Source endpoint queued replay'))
    before=_fingerprint()
    app=FastAPI();app.include_router(router)
    writes=[]
    def capture(connection,cursor,statement,parameters,context,executemany):
        if statement.lstrip().split()[0].upper() in {'UPDATE','INSERT','DELETE','CREATE','DROP','ALTER'}:writes.append(statement)
    event.listen(db.engine,'before_cursor_execute',capture)
    try:response=TestClient(app).get('/api/tour/source')
    finally:event.remove(db.engine,'before_cursor_execute',capture)
    assert response.status_code==200,response.text
    assert response.json()==source_identity()
    assert _fingerprint()==before
    assert writes==[]


def test_generated_real_bundle():
    root=Path(__file__).resolve().parents[2]
    bundle=json.loads((root/'frontend/public/tour-bundle.json').read_text(encoding='utf-8'))
    verify_bundle(bundle,source_identity())
    assert bundle['meta']['product_count']==75
    assert bundle['base']['detail']['plan']['stage']=='discover'
    assert bundle['questions']=={'why':None,'heat':None} or all(bundle['questions'].values())
    report=json.loads((root/'reports/night4/bundle-build.json').read_text(encoding='utf-8'))
    assert report['public_unchanged']
    assert report['provider_calls']==0


def test_recording_schema_is_independent():
    root=Path(__file__).resolve().parents[2]
    report=json.loads((root/'reports/night4/bundle-build.json').read_text(encoding='utf-8'))
    schema=report['schema_name']
    assert schema.startswith('tour_recording_')
    with db.engine.connect() as c:
        assert c.execute(text('SELECT to_regclass(:table)'),{'table':schema+'.ground_truth_events'}).scalar() is None
        sequence=c.execute(text("SELECT pg_get_serial_sequence(:table,'id')"),{'table':schema+'.decisions'}).scalar()
        assert sequence.startswith(schema+'.')


def test_recorded_answers_are_genuine_grounded_and_on_their_branch():
    from scoop.ai.grounding import mismatches
    root=Path(__file__).resolve().parents[2]
    bundle=json.loads((root/'frontend/public/tour-bundle.json').read_text(encoding='utf-8'))
    for answer,snapshot in [(a,bundle['base']) for a in bundle['questions'].values()]+[(b['answer'],b['snapshot']) for b in bundle['branches'].values()]:
        assert answer and answer['provider']=='gemini'
        assert answer['model']=='gemini-3.8-flash'
        assert answer['usage']['input_tokens']>0
        assert answer['grounding']['passed']
        assert mismatches(answer['grounding']['claims'],answer['grounding']['evidence'])==[]
        digest=hashlib.sha256(json.dumps(snapshot,sort_keys=True,default=str,separators=(',',':')).encode()).hexdigest()
        assert answer['snapshot_hash']==digest
        assert answer['source_order_hash']==snapshot['simulation']['order_hash']
