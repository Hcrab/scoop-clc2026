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
from scoop.tour_recalculation import enrich_bundle, cohort_factor, recalculation, heat_temperature


def fixture_bundle():
    source={'default_week':'2026-07-27','default_order_hash':'original','plan_id':'P20260727'}
    def snapshot(n):
        return {'detail':{'orders':[{'sku':'A','name':'Strawberry','effective_cases':n,'capacity_cut_cases':0}],
                          'plan':{'summary':{'cohort_model':{'units':[{'sku':'A','leaf_id':'C','expected_recent':10}],
                                                            'sku_factors':{'A':{'f50':n}}}}}},
                'order_summary':{'capacity':{'projected_peak_pallets':n+0.5}},
                'simulation':{'status':'ready','result':{'demand':[[n]],'runs':{'scoop':{'actual':n,'per_sku':{'demand':[[n]]}},'baseline':{'per_sku':{'demand':[[n]]}}},'summary':{'scoop':{'lost_units':n}}}}}
    bundle={'version':1,**source,'meta':{'strawberry_card_id':'C','strawberry_skus':['A']},
            'base':snapshot(1),'branches':{k:{'snapshot':snapshot(n)} for n,k in enumerate(['unchanged','summer','growing'],1)}}
    enrich_bundle(bundle,34.5)
    bundle['version']=3
    from scoop.tour_worlds import multiplier,prove_replay,digest
    for name,branch in bundle['branches'].items():
        branch['future']={'branch':name,'matched_skus':['A'],'history_hash':'history','outside_cohort_hash':'outside','weather_hash':'weather',
            'original_demand_hash':'original','demand_hash':'original' if name=='unchanged' else name,
            'unchanged_physical_equal':name=='unchanged','persisted_replays_cleared':True,
            'baseline_context_control_hash':digest(branch['snapshot']['simulation']['result']['runs']['baseline']),
            'multipliers':{day:str(multiplier(name,day)) for day in ('2026-07-27','2026-08-10','2026-08-11')},
            **prove_replay(branch['snapshot']['simulation']['result'])}
    return bundle,source


def test_v3_metadata_is_required_and_must_match_recorded_values():
    bundle,source=fixture_bundle()
    for invalid in (1,2,None):
        changed=deepcopy(bundle);changed['version']=invalid
        with pytest.raises(ValueError,match='Unsupported'):
            verify_bundle(changed,source)
    for temperature in (None,True,float('nan'),'34.5'):
        changed=deepcopy(bundle);changed['meta']['heat_temp']=temperature
        with pytest.raises(ValueError,match='heat temperature'):
            verify_bundle(changed,source)
    for key in ('f_before','f_after','before','after','p_before','p_after','n','trimmed_products'):
        changed=deepcopy(bundle);changed['branches']['summer']['recalculation'].pop(key)
        with pytest.raises(ValueError,match='recalculation metadata'):
            verify_bundle(changed,source)


def test_factor_uses_actual_sku_factors_and_only_matched_expected_demand():
    bundle,_=fixture_bundle();snapshot=bundle['base']
    model=snapshot['detail']['plan']['summary']['cohort_model']
    model['units']=[{'sku':'A','leaf_id':'C','expected_recent':3},
                    {'sku':'A','leaf_id':'C','expected_recent':2},
                    {'sku':'B','leaf_id':'C','expected_recent':15},
                    {'sku':'A','leaf_id':'OTHER','expected_recent':10000}]
    model['sku_factors']={'A':{'f50':1.2},'B':{'f50':1.6}}
    assert cohort_factor(snapshot,'C',['A','B'])==pytest.approx(1.5)


def test_only_new_capacity_cuts_are_counted():
    bundle,_=fixture_bundle();base=bundle['base'];after=deepcopy(base)
    base['detail']['orders'][0]['capacity_cut_cases']=2
    after['detail']['orders'][0].update(capacity_cut_cases=5,effective_cases=0)
    result=recalculation(base,after,'C',['A'])
    assert result['n']==3
    assert result['trimmed_products']==[{'sku':'A','name':'Strawberry','cases_trimmed':3,'before_cut':2,'after_cut':5}]
    after['detail']['orders'][0]['capacity_cut_cases']=1
    assert recalculation(base,after,'C',['A'])['n']==0
    after['detail']['orders'][0]['capacity_cut_cases']=2
    assert recalculation(base,after,'C',['A'])['trimmed_products']==[]


def test_enrichment_preserves_all_recorded_content():
    bundle,_=fixture_bundle()
    bundle['version']=1
    bundle['meta'].pop('heat_temp')
    for branch in bundle['branches'].values():
        branch.pop('recalculation')
    bundle['questions']={'why':{'text':'accepted answer','snapshot_hash':'unchanged'}}
    original=deepcopy(bundle)
    enrich_bundle(bundle,35.2)
    assert bundle['base']==original['base']
    assert bundle['questions']==original['questions']
    for key,branch in bundle['branches'].items():
        assert {k:v for k,v in branch.items() if k!='recalculation'}==original['branches'][key]
    once=deepcopy(bundle)
    enrich_bundle(bundle,35.2)
    assert bundle==once


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
        enrich_bundle(bundle,bundle['meta']['heat_temp']);bundle['version']=3
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
    if bundle.get('version') != 3:
        pytest.skip('Run scripts/build-tour-bundle.py to generate the version 3 bundle')
    verify_bundle(bundle,source_identity())
    assert bundle['meta']['product_count']==75
    assert bundle['meta']['heat_temp']==heat_temperature(db.engine,bundle['meta']['heat_date'])
    assert bundle['base']['detail']['plan']['stage']=='discover'
    assert bundle['questions']=={'why':None,'heat':None} or all(bundle['questions'].values())
    report=json.loads((root/'data/tour/bundle-build.json').read_text(encoding='utf-8'))
    assert report['public_unchanged']
    assert report['provider_calls']==0


def test_recording_schema_is_independent():
    root=Path(__file__).resolve().parents[2]
    report=json.loads((root/'data/tour/bundle-build.json').read_text(encoding='utf-8'))
    if report.get('version') != 3:
        pytest.skip('Run scripts/build-tour-bundle.py to generate the version 3 recording schema')
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
    if bundle.get('version') != 3:
        pytest.skip('Run scripts/record-tour-answers.py to generate the version 3 question evidence')
    for answer,snapshot in [(a,bundle.get('question_evidence',bundle['base'])) for a in bundle['questions'].values()]:
        assert answer and answer['provider']=='gemini'
        assert answer['model']=='gemini-3.8-flash'
        assert answer['usage']['input_tokens']>0
        assert answer['grounding']['passed']
        assert mismatches(answer['grounding']['claims'],answer['grounding']['evidence'])==[]
        digest=hashlib.sha256(json.dumps(snapshot,sort_keys=True,default=str,separators=(',',':')).encode()).hexdigest()
        assert answer['snapshot_hash']==digest
        assert answer['source_order_hash']==snapshot['simulation']['order_hash']
