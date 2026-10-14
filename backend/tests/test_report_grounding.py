from copy import deepcopy

import pytest

from test_weekly_review import api, cohort_cards, presentation, report, saved_cards
from scoop.ai import weekly
from scoop.ai.grounding import mismatches
from scoop.ai.report_design import validate
from scoop.models import Plan


def test_wrong_number_is_rejected_and_claim_scope_is_cited_only(api):
    _,scope,_,_=api
    with scope() as session:
        plan=session.get(Plan,'TESTAPI')
        claim=report();claim['claims'][0]['text']='The cohort effect is 81%.'
        claim['claims'][0]['evidence_ids']=['Q-cohort-leaf-0']
        with pytest.raises(weekly.GroundingError) as exc:
            weekly._finish(session,plan,claim,[{'id':'Q1','name':'query_group','args':{},'result':{'effect_pct':81}}])
        assert exc.value.errors[0]['number']=='81%'
        assert exc.value.errors[0]['evidence_ids']==['Q-cohort-leaf-0']


def test_rounding_percent_ratio_dates_and_ids_are_legitimate():
    evidence={'Q1':{'effect_pct':12.34,'share':.125,'requested_units':1234,
                    'date':'2026-07-05','sku':'IC001'}}
    claims=[{'text':'Q1: IC001 rose 12.3% on 2026-07-05; 1,234 units and a 12.5% share.',
             'evidence_ids':['Q1']}]
    assert mismatches(claims,evidence)==[]
    assert mismatches([{'text':'The increase is -12.3%.','evidence_ids':['Q1']}],evidence)


def test_chart_specs_use_saved_series_and_reject_svg_or_unmeasured_series():
    evidence={'Q1':{'daily':[{'date':'2026-07-05','requested_units':18,'expected_units':10}]},
              'F1':{'actual_share':.3,'expected_share':.2}}
    spec=presentation()
    spec['html']='<figure data-chart="line" data-evidence-id="Q1" data-series="actual,expected"><figcaption>Requests</figcaption></figure>'
    assert 'data-chart' in validate(spec,evidence,evidence)['html']
    spec['html']='<figure data-chart="line" data-evidence-id="F1" data-series="actual,expected"></figure>'
    validate(spec,evidence,evidence)
    spec['html']='<figure data-chart="line" data-evidence-id="Q1" data-series="actual,prior"></figure>'
    with pytest.raises(ValueError):validate(spec,evidence,evidence)
    spec['html']='<svg><path d="M0 1"/></svg>'
    with pytest.raises(ValueError):validate(spec,evidence,evidence)
    spec['html']='<div style="width:80%">Chart</div>'
    with pytest.raises(ValueError):validate(spec,evidence,evidence)


def test_one_grounding_repair_then_offline_with_queries_and_usage(api):
    _,scope,_,_=api
    calls=[]
    def wire(payload):
        calls.append(deepcopy(payload))
        if len(calls)==1:
            bad=report();bad['claims'][0]['text']='The cohort effect is 81%.'
            bad['claims'][0]['evidence_ids']=['Q-cohort-leaf-0']
        else:
            response=payload['contents'][-1]['parts'][0]['functionResponse']['response']
            assert response['mismatches'][0]['number']=='81%'
            bad=report();bad['claims'][0]['text']='The cohort effect is 82%.'
            bad['claims'][0]['evidence_ids']=['Q-cohort-leaf-0']
        bad['presentation']=presentation('Q-cohort-leaf-0')
        return {'usageMetadata':{'promptTokenCount':10,'candidatesTokenCount':5},
                'candidates':[{'content':{'role':'model','parts':[
                    {'functionCall':{'name':'finish_weekly_review','args':bad}}]}}]}
    with scope() as session:
        plan=session.get(Plan,'TESTAPI')
        result=weekly.investigate(session,plan,wire)
    assert len(calls)==2
    assert result['status']=='offline'
    assert result['grounding_failure']['repair_attempted']
    assert result['grounding_failure']['mismatches'][0]['number']=='82%'
    assert result['queries'][0]['id']=='Q-cohort-leaf-0'
    assert result['usage']=={'input_tokens':20,'output_tokens':10}


def test_corrected_repair_succeeds_without_extra_round(api):
    _,scope,_,_=api
    count=0
    def wire(payload):
        nonlocal count
        count+=1
        output=report();output['claims'][0]['evidence_ids']=['Q-cohort-leaf-0']
        output['claims'][0]['text']=f'The cohort effect is {81 if count==1 else 80}%.'
        output['presentation']=presentation('Q-cohort-leaf-0')
        return {'candidates':[{'content':{'role':'model','parts':[
            {'functionCall':{'name':'finish_weekly_review','args':output}}]}}]}
    with scope() as session:
        result=weekly.investigate(session,session.get(Plan,'TESTAPI'),wire)
    assert count==2 and result['status']=='complete'


@pytest.mark.parametrize('field',['report','title','html'])
def test_visible_wrong_number_with_valid_structured_claims_repairs_once_then_falls_back(api,field):
    _,scope,_,_=api
    calls=[]
    def wire(payload):
        calls.append(payload)
        output=report()
        output['claims'][0]['evidence_ids']=['Q-cohort-leaf-0']
        output['claims'][0]['text']='The cohort effect is 80%.'
        output['presentation']=presentation('Q-cohort-leaf-0')
        wrong='The cohort effect is 98765%.'
        if field=='report':output['report']=wrong
        else:output['presentation'][field]=f'<p>{wrong}</p>' if field=='html' else wrong
        return {'candidates':[{'content':{'role':'model','parts':[
            {'functionCall':{'name':'finish_weekly_review','args':output}}]}}]}
    with scope() as session:
        result=weekly.investigate(session,session.get(Plan,'TESTAPI'),wire)
    assert len(calls)==2 and result['status']=='offline'
    assert result['grounding_failure']['repair_attempted']
    assert any(m['number']=='98765%' for m in result['grounding_failure']['mismatches'])


def test_counts_cannot_substantiate_percentages():
    assert mismatches([{'text':'Demand rose 100%.','evidence_ids':['Q1']}],{'Q1':{'sku_count':1,'units':100}})
    assert not mismatches([{'text':'Demand rose 100%.','evidence_ids':['Q1']}],{'Q1':{'effect_pct':100}})


def test_empty_key_displays_card_list_even_with_saved_ai_report(api,monkeypatch):
    _,scope,_,_=api
    monkeypatch.setenv('GEMINI_API_KEY','')
    with scope() as session:
        plan=session.get(Plan,'TESTAPI')
        plan.summary={**plan.summary,'weekly_review':{'status':'complete','report':'Saved AI prose',
                       'presentation':{'title':'Saved AI report','html':'<p>Old report</p>','css':''}}}
        result=weekly.display_view(plan)
        assert result['status']=='offline'
        assert 'data-report-card' in result['presentation']['html']
        assert 'Old report' not in result['presentation']['html']
        assert 'error' not in result
        assert plan.summary['weekly_review']['status']=='complete'


def test_natural_date_ranges_use_cited_window_dates():
    evidence={'Q1':{'window_recent':['2026-07-13','2026-07-26'],'effect_pct':12.3}}
    assert not mismatches([{'text':'Requests rose 12.3% over 13–26 Jul 2026.','evidence_ids':['Q1']}],evidence)
    assert mismatches([{'text':'Requests rose 12.3% over 13–27 Jul 2026.','evidence_ids':['Q1']}],evidence)
