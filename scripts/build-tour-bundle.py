"""Record the actual tour API on a private PostgreSQL schema, never public writes.

Run with .venv/Scripts/python.exe scripts/build-tour-bundle.py. The retained
schema is reported for the separate, explicitly authorized AI recording phase.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'backend'))


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,default=str,separators=(',',':')).encode()).hexdigest()


def fingerprint(engine):
    """All public table rows, including settings, plans and cached replay state."""
    from sqlalchemy import text
    with engine.connect() as c:
        names=c.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")).scalars().all()
        return {name:c.execute(text(f'SELECT md5(COALESCE(string_agg(row_hash,\'\' ORDER BY row_hash),\'\')) FROM (SELECT md5(row_to_json(t)::text) row_hash FROM public."{name}" t) x')).scalar() for name in names}


def build(output):
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    from scoop import db
    from scoop.models import Base
    from scoop.demo_config import DEMO_WEEK, DEMO_SEED
    public=db.engine
    before=fingerprint(public)
    schema='tour_recording_'+uuid4().hex[:16]
    report={'schema_name':schema,'started_at':time.time(),'public_before':before,'provider_calls':0,'requests':[],
            'excluded_source_tables':['ground_truth_events'],'source_hashes':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__).resolve(),ROOT/'backend/scoop/tour_bundle.py',ROOT/'backend/scoop/api/tour.py']}}
    report_path=ROOT/'reports/night4/bundle-build.json'
    report_path.parent.mkdir(parents=True,exist_ok=True)
    # Create independent serial sequences, indexes and constraints via ORM DDL.
    private=create_engine(public.url,connect_args={'options':f'-csearch_path={schema}'},pool_pre_ping=True)
    with public.begin() as c: c.execute(text(f'CREATE SCHEMA "{schema}"'))
    Base.metadata.create_all(private.execution_options(schema_translate_map={None:schema}),
                             tables=[t for t in Base.metadata.sorted_tables if t.name!='ground_truth_events'])
    # Set both globals before importing any consumers with captured engine defaults.
    db.engine=private
    db.SessionLocal=sessionmaker(bind=private,expire_on_commit=False)
    from scoop.demo_worlds import PLANNING
    with private.begin() as c:
        seed=c.execute(text("SELECT value FROM public.settings WHERE key='seed'")).scalar()
        if int(seed or 0)!=DEMO_SEED: raise ValueError('Public immutable default world is required')
        template=c.execute(text('SELECT value FROM public.settings WHERE key=:k'),{'k':f'initial_{DEMO_SEED}_{DEMO_WEEK}'}).scalar()
        if not template or not json.loads(template)['complete']: raise ValueError('Complete clean initial template is required')
        for table in Base.metadata.sorted_tables:
            if table.name in PLANNING or table.name=='ground_truth_events': continue
            name=table.name
            c.execute(text(f'INSERT INTO "{schema}"."{name}" SELECT * FROM public."{name}"'))
        c.execute(text("DELETE FROM settings WHERE key='cohort_overrides'"))
    # Route the shared globals before importing API/algorithm consumers.
    db.engine=private
    db.SessionLocal=sessionmaker(bind=private,expire_on_commit=False)
    # demo_worlds was imported only for constants; replace its captured engine and manager.
    import scoop.demo_worlds as worlds
    worlds.engine=private
    worlds.manager=worlds.WorldManager(private,active_schema=schema,namespace=schema+'_snap')
    worlds.manager.tables=[t for t in worlds.manager.tables if t.name!='ground_truth_events']
    import scoop.demo_reset as reset
    reset.engine=private
    # Fail closed if any recording route unexpectedly tries a live provider.
    from scoop.ai import gemini
    def no_provider(*args,**kwargs):
        report['provider_calls']+=1
        raise AssertionError('Provider calls are forbidden during bundle recording')
    gemini._wire=no_provider
    from scoop.main import app
    from fastapi.testclient import TestClient
    from scoop.tour_bundle import source_identity, verify_bundle
    from scoop.tour_recalculation import enrich_bundle, heat_temperature
    from scoop.demo_config import DEMO_SCENARIO
    client=TestClient(app) # no startup hook; this process owns only its cloned work
    prefix='/api/plans/P20260727'
    def api(method,path,body=None):
        started=time.monotonic()
        response=client.request(method,path,json=body) if body is not None else client.request(method,path)
        report['requests'].append({'method':method,'route':path,'status':response.status_code,'seconds':round(time.monotonic()-started,3)})
        if response.status_code!=200: raise RuntimeError(f'{method} {path}: {response.status_code} {response.text[:600]}')
        return response.json()
    def fresh():
        worlds.clear_runtime_caches()
        api('POST','/api/demo-settings/reset',{'scenario_id':DEMO_SCENARIO,'week_start':DEMO_WEEK})
    def wait_replay():
        deadline=time.monotonic()+600
        while time.monotonic()<deadline:
            result=api('GET',prefix+'/simulation')
            if result['status']=='ready': return result
            if result['status']=='failed': raise RuntimeError(result.get('error'))
            time.sleep(.5)
        raise TimeoutError('Actual replay did not complete in 600 seconds')
    def snapshot():
        return {'detail':api('GET',prefix),'cohorts':api('GET',prefix+'/cohorts'),
                'direction_preview':api('POST',prefix+'/direction-preview',{'service_level':None}),
                'order_summary':api('GET',prefix+'/order-summary'),'dashboard':api('GET',prefix+'/dashboard'),
                'simulation':wait_replay()}
    def cases(detail,skus=None):
        return sum(o['effective_cases'] for o in detail['orders'] if skus is None or o['sku'] in skus)
    def prepare():
        api('POST',prefix+'/advance');api('POST',prefix+'/approve-orders');return wait_replay()
    try:
        fresh()
        source=source_identity(private,schema)
        assert api('GET','/api/tour/source')==source
        common={'bootstrap':api('GET','/api/bootstrap'),'settings':api('GET','/api/demo-settings')}
        first=api('GET',prefix)
        card=next(c for c in first['cohort_cards'] if 'strawberry' in c['name'].lower())
        skus=card['skus'];cid=card['id']
        print('Private schema:',schema,'strawberry:',cid,flush=True)
        prepare()
        # Pair the actual pre-approval report with its complete recorded replay.
        base=snapshot();base['detail']=first
        steps=card['drilldown']['steps']
        report['strawberry_card']=card
        meta={'capacity':common['bootstrap']['node']['capacity_pallets'],'product_count':len(common['bootstrap']['products']),
              'strawberry_card_id':cid,'strawberry_skus':skus,'effect':round(card['effect_pct']),
              **{f'l{i+1}':round(step.get('effect_pct',step.get('effect',0))) for i,step in enumerate(steps[:3])},'heat_date':'2026-07-30'}
        contexts={'unchanged':None,'summer':{'cohort':cid,'type':'ends_on','value':'2026-08-10'},
                  'growing':{'cohort':cid,'type':'expect','value':{'pct':card['interval_pct'][1]/100,'strength':'high'},
                             'note':'Optimistic user-context preset: existing model 80% interval upper endpoint, high confidence.'}}
        bundle={'version':2,**source,'meta':meta,'common':common,'base':base,'branches':{},'questions':{'why':None,'heat':None}}
        for name,context in contexts.items():
            fresh();before_detail=api('GET',prefix)
            edit=api('POST',prefix+'/overrides',context) if context else None
            report_detail=api('GET',prefix)
            prepare();snap=snapshot();snap['detail']=report_detail
            replay=snap['simulation']['result']
            events=replay['events']
            arrivals=[e for e in events if e['kind']=='arrival' and e.get('sku') in skus and e.get('policy','scoop')=='scoop']
            stockouts=[e for e in events if e['kind']=='stockout' and e.get('policy','scoop')=='scoop']
            def moment(event,arrival=False):
                if not event:return None
                minute=event['minute'];result={'date':event['date'],'time':f'{minute//60:02d}:{minute%60:02d}','minute':minute}
                if arrival:result['units']=event.get('units')
                else:result['product']=next((p['name'] for p in replay['products'] if p['sku']==event.get('sku')),event.get('sku'))
                return result
            branch={'id':name,'context':context,'snapshot':snap,'edit':edit,'before_cases':cases(before_detail,skus),
                    'after_cases':cases(report_detail,skus),'total_cases':cases(report_detail),
                    'peak':snap['order_summary']['capacity']['projected_peak_pallets'],'capacity':meta['capacity'],'answer':None,
                    'moments':{'heat_date':meta['heat_date'],'strawberry_arrival':moment(arrivals[0] if arrivals else None,True),
                               'stockout':moment(stockouts[0] if stockouts else None)},'widgets':{}}
            for choice,title,scope,metric in [('stock','Strawberry stock',{'kind':'cohort','key':cid},'on_hand'),
                    ('space','Cold-store space',{'kind':'warehouse','key':''},'pallets'),
                    ('cover','Products closest to running out',{'kind':'warehouse','key':''},'lowest_cover')]:
                existing={w['title'] for w in snap['dashboard']['widgets']}
                if title in existing:title+=' · Tour choice'
                spec={'title':title,'scope':scope,'metric':metric,'threshold':None}
                physical_before=api('GET',prefix+'/simulation')['order_hash']
                added=api('POST',prefix+'/dashboard',spec)
                branch['widgets'][choice]={'spec':spec,'dashboard':api('GET',prefix+'/dashboard'),'edit':added}
                api('POST',prefix+f"/edits/{added['edit_id']}/undo")
                assert api('GET',prefix+'/simulation')['order_hash']==physical_before,'Widget changed physical orders'
            bundle['branches'][name]=branch
            print(name,branch['before_cases'],branch['after_cases'],branch['total_cases'],replay['summary']['scoop'],flush=True)
        enrich_bundle(bundle, heat_temperature(private, meta['heat_date']))
        verify_bundle(bundle,source)
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(bundle,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n',encoding='utf-8')
        report.update(status='complete',source=source,bytes=output.stat().st_size,bundle_hash=digest(bundle),
                      growing_preset=contexts['growing'],branches={k:{field:b[field] for field in ('before_cases','after_cases','total_cases','peak','moments')} for k,b in bundle['branches'].items()})
    except Exception as exc:
        report.update(status='failed',error=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        report['public_after']=fingerprint(public)
        report['public_unchanged']=report['public_after']==before
        report['elapsed_seconds']=time.time()-report['started_at']
        report_path.write_text(json.dumps(report,indent=2,default=str)+'\n',encoding='utf-8')
        assert report['public_unchanged'],'Public schema changed during build'

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'frontend/public/tour-bundle.json')
    args=parser.parse_args();build(args.output.resolve())
