"""Record five real Gemini tour answers through the normal assistant API.

Run build-tour-bundle.py first. Reuses its isolated schema; never changes public.
Existing accepted answers are kept unless --replace is explicitly supplied.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
os.environ.setdefault('OMP_NUM_THREADS','1')


def run(only=None,replace=False):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from scoop import db
    from scoop.config import settings
    from scoop.ai.usage import summary
    spec=importlib.util.spec_from_file_location('tour_builder',ROOT/'scripts/build-tour-bundle.py')
    builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
    public=db.engine
    before=builder.fingerprint(public)
    build=json.loads((ROOT/'reports/night4/bundle-build.json').read_text())
    schema=build['schema_name']
    if not re.fullmatch('tour_recording_[a-f0-9]{16}',schema):raise ValueError('Expected isolated recording schema')
    private=create_engine(public.url,connect_args={'options':f'-csearch_path={schema}'},pool_pre_ping=True)
    db.engine=private;db.SessionLocal=sessionmaker(bind=private,expire_on_commit=False)
    import scoop.demo_worlds as worlds
    worlds.engine=private
    worlds.manager=worlds.WorldManager(private,active_schema=schema,namespace=schema+'_snap')
    worlds.manager.tables=[t for t in worlds.manager.tables if t.name!='ground_truth_events']
    import scoop.demo_reset as reset
    reset.engine=private
    from scoop.main import app
    from scoop.demo_config import DEMO_SCENARIO,DEMO_WEEK
    from scoop.ai.grounding import mismatches
    from scoop.ai.tools import context as assistant_context
    from scoop.models import Plan
    from scoop.simulation_jobs import order_hash
    from fastapi.testclient import TestClient
    client=TestClient(app)
    path=ROOT/'frontend/public/tour-bundle.json'
    bundle=json.loads(path.read_text(encoding='utf-8'))
    prefix='/api/plans/'+bundle['plan_id']
    report_path=ROOT/'reports/night4/recorded-answers.json'
    report=json.loads(report_path.read_text()) if report_path.exists() else {'budget_start':summary(),'recordings':{}}
    report.update(model=settings.gemini_model,schema_name=schema,public_before=before,status='recording')
    def save():
        report['budget_end']=summary()
        report['public_after']=builder.fingerprint(public)
        report['public_unchanged']=before==report['public_after']
        report_path.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        assert report['public_unchanged'],'Recording changed public tables'
    def api(method,path,body=None):
        response=client.request(method,path,json=body) if body is not None else client.request(method,path)
        if response.status_code!=200:raise RuntimeError(f'{method} {path}: {response.status_code} {response.text[:500]}')
        return response.json()
    def physical():
        with db.SessionLocal() as session:return order_hash(session,session.get(Plan,bundle['plan_id']))
    def quantities(detail):return sorted((o['sku'],o['effective_cases']) for o in detail['orders'])
    labels={'why':'Why strawberry, and why now?','heat':'Could this just be the heat?',
            'summer':'A summer one-off, ending 10 Aug','growing':'I expect it to keep growing','unchanged':'Nothing to add'}
    try:
        for name,label in labels.items():
            if only and name not in only:continue
            target=bundle['questions'] if name in ('why','heat') else bundle['branches'][name]
            key=name if name in ('why','heat') else 'answer'
            if target.get(key) and not replace:continue
            worlds.clear_runtime_caches()
            api('POST','/api/demo-settings/reset',{'scenario_id':DEMO_SCENARIO,'week_start':DEMO_WEEK})
            branch=bundle['branches'].get(name)
            edit=api('POST',prefix+'/overrides',branch['context']) if branch and branch['context'] else None
            detail=api('GET',prefix)
            expected=branch['snapshot'] if branch else bundle['base']
            assert quantities(detail)==quantities(expected['detail']),'Recording snapshot orders differ from bundle'
            before_hash=physical()
            with db.SessionLocal() as session:
                evidence={'snapshot':assistant_context(session,session.get(Plan,bundle['plan_id'])),
                          'saved_report':detail}
            if edit:evidence['context_result']=edit
            request=label+'\nAnswer in English, in at most three short sentences. Explain from this saved plan and its evidence; do not change any orders, context, or widgets.'
            request+=' Focus on the highlighted value-price strawberry water-ice cohort, including what the weather-adjusted expectation does and does not explain.'
            if branch:
                request+=' This context option has already been applied to this snapshot (or left unchanged for Nothing to add); explain the saved result, without applying it again.'
                request+=f" For the context confirmation, use the actual saved strawberry order total: {branch['before_cases']} cases before the choice and {branch['after_cases']} cases after it. The report's original +134-case uplift is an earlier state; it is not this context edit's change."
            previous=report['recordings'].get(name)
            attempts=[]
            for attempt in range(2):
                started=time.monotonic()
                response=api('POST',prefix+'/chat',{'stage':'discover','message':request})
                if response['provider']!='gemini' or response.get('fallback_reason'):
                    raise RuntimeError('Recording must be a complete real Gemini response: '+str(response.get('fallback_reason')))
                assert physical()==before_hash,'Assistant unexpectedly changed physical orders'
                # Add the real numeric tool responses used by the normal path.
                for i,trace in enumerate(response.get('tool_trace',[])):evidence[f'tool_{i}']=trace
                claims=[{'text':response['reply'],'evidence_ids':list(evidence)}]
                errors=mismatches(claims,evidence)
                sentence_count=len([s for s in re.split(r'(?<=[.!?])\s+(?=[A-Z])',response['reply'].strip()) if s])
                attempts.append({'response':response,'grounding_errors':errors,'sentences':sentence_count,'seconds':round(time.monotonic()-started,3)})
                report['recordings'][name]={'question':label,'request':request,'attempts':attempts}
                if previous:report['recordings'][name]['previous_recording']=previous
                save()
                if not errors and sentence_count<=3:
                    target[key]={'reply':response['reply'],'provider':response['provider'],'model':settings.gemini_model,
                                 'usage':response['usage'],'tool_trace':response['tool_trace'],
                                 'grounding':{'passed':True,'claims':claims,'evidence':evidence},
                                 'snapshot_hash':builder.digest(expected),'source_order_hash':before_hash}
                    path.write_text(json.dumps(bundle,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n',encoding='utf-8')
                    report['recordings'][name]['accepted']=True
                    print(name+': '+response['reply'],flush=True)
                    break
                if attempt:raise ValueError(f'{name}: recording failed grounding/length after one repair: {errors}')
                request+=' Regenerate in no more than THREE SHORT SENTENCES. Use only the supplied evidence values.'
                if errors:request+=' Correct these quantitative mismatches: '+json.dumps(errors)
            save()
        report['status']='complete' if all(bundle['questions'].values()) and all(b['answer'] for b in bundle['branches'].values()) else 'partial'
        report['bundle_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    finally:save()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--only',nargs='+',choices=['why','heat','summer','growing','unchanged'])
    parser.add_argument('--replace',action='store_true')
    args=parser.parse_args();run(args.only,args.replace)
