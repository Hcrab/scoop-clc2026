import json
from copy import deepcopy
import pytest
from test_api_state import api
from scoop.ai import weekly,gemini,chat
from scoop.models import Plan,ChatMessage


def presentation(evidence_id='Q1'):
    return {'title':'A localized demand shift merits a closer look',
            'html':f'<article><h1>A localized demand shift merits a closer look</h1><p>Demand differs from its comparison.</p><details data-evidence-id="{evidence_id}"><summary>Inspect the demand evidence</summary></details></article>',
            'css':'article { background: #fffdf9; padding: 1.5rem; } h1 { color: #25836b; } details:focus-within { outline: 2px solid #9486b1; } @media (max-width: 600px) { article { padding: 1rem; } }'}

def saved_cards(count=1):
    return [{'id':f'leaf-{i}','name':'A × B × C','effect_pct':80.,'interval_pct':[65.,95.],
             'case_change':4,'pallet_change':.4,'skus':['x','y','z'],'districts':['Kowloon'],
             'method':{'leaf':{'id':f'leaf-{i}'},'units':[]}} for i in range(count)]

@pytest.fixture(autouse=True)
def cohort_cards(api):
    _,scope,_,_=api
    with scope() as session:
        plan=session.get(Plan,'TESTAPI');plan.summary={**plan.summary,'cohort_cards':saved_cards()}

def test_cohort_cards_supplied_citable_and_not_charged_to_query_allowance(api,monkeypatch):
    from scoop.ai import exploration_tools
    _,scope,_,_=api
    cards=saved_cards(weekly.MAX_QUERIES+1)
    calls=[]
    monkeypatch.setattr(exploration_tools,'execute',lambda *args:{'recent':{'requested_units':180}})
    def wire(payload):
        source=json.loads(payload['contents'][0]['parts'][0]['text'].split('\nInvestigate')[0])
        assert len(source['cohort_cards'])==len(cards)
        assert source['cohort_cards'][0]['result']=={k:v for k,v in cards[0].items() if k!='method'}
        calls.append(payload)
        if len(calls)==1:
            parts=[{'functionCall':{'name':'query_group','args':{'group_ids':['a','b','c']}}}]
        else:
            result=report();result['presentation']=presentation('Q-cohort-leaf-0')
            result['claims'][0]['evidence_ids']=['Q-cohort-leaf-0','Q1']
            parts=[{'functionCall':{'name':'finish_weekly_review','args':result}}]
        return {'candidates':[{'content':{'role':'model','parts':parts}}]}
    with scope() as session:
        plan=session.get(Plan,'TESTAPI');plan.summary={**plan.summary,'cohort_cards':cards}
        result=weekly.investigate(session,plan,wire=wire)
        assert result['status']=='complete'
        assert result['queries'][0]['id']=='Q1'
        evidence=next(q for q in result['queries'] if q['id']=='Q-cohort-leaf-0')
        assert evidence['result']==cards[0]
        assert result['claims'][0]['evidence_ids']==['Q-cohort-leaf-0','Q1']

def test_cohort_cards_available_with_offline_ai(api,monkeypatch):
    client,scope,_,_=api
    cards=saved_cards()
    with scope() as session:
        plan=session.get(Plan,'TESTAPI');plan.summary={**plan.summary,'cohort_cards':cards}
    monkeypatch.setattr(chat,'provider_info',lambda:{'live':False})
    client.post('/api/plans/TESTAPI/review')
    detail=client.get('/api/plans/TESTAPI').json()
    assert detail['review']['status']=='offline'
    assert detail['review']['queries'][0]['result']==cards[0]

def report():
    return {'report':'A localized change in the combination merits further context. Check the local purchasing context before changing quantities.',
            'presentation':presentation(),
            'claims':[{'text':'The combination differs from its parent category.','kind':'observation','evidence_ids':['Q1']}],
            'questions':[{'text':'Was there a local promotion for these products this week?','finding_id':None}]}

def test_live_loop_saves_evidence_questions_and_preserves_business(api,monkeypatch):
    from scoop.ai import exploration_tools
    c,scope,_,_=api
    before=c.get('/api/plans/TESTAPI').json()
    calls=[]
    def execute(name,args,session,plan):
        calls.append((name,args));return {'units':20,'cutoff':'2026-07-05'}
    monkeypatch.setattr(exploration_tools,'execute',execute)
    def wire(payload):
        assert payload['generationConfig']['maxOutputTokens']>=8192
        if not calls:
            parts=[{'functionCall':{'name':'query_group','args':{'group_ids':['a','b']}}},
                   {'functionCall':{'name':'query_operations','args':{'group_ids':['a','b']}}}]
        else:parts=[{'functionCall':{'name':'finish_weekly_review','args':report()}}]
        return {'modelVersion':'fixture-model','candidates':[{'content':{'role':'model','parts':parts}}]}
    monkeypatch.setattr(gemini,'_wire',wire)
    monkeypatch.setattr(chat,'provider_info',lambda:{'live':True})
    result=c.post('/api/plans/TESTAPI/review').json()
    assert result['status']=='complete' and len(result['queries'])==3
    after=c.get('/api/plans/TESTAPI').json()
    assert after['review']['model']=='fixture-model'
    assert after['review']['presentation']==presentation()
    assert after['discussion']['open_count']==1
    assert after['discussion']['items'][0]['title']==report()['questions'][0]['text']
    for key in ['orders','directions','questions','decisions','watch']:
        assert before[key]==after[key],key
    c.post('/api/plans/TESTAPI/review')
    assert len(calls)==2 # Reload or repeat never silently spends again.
    assert c.post('/api/plans/TESTAPI/advance').status_code==200
    assert c.get('/api/plans/TESTAPI').json()['discussion']==after['discussion']

def test_report_checks_evidence_without_policing_natural_language(api):
    _,scope,_,_=api
    queries=[{'id':'Q1','name':'query_group','args':{'group_ids':['a','b']},'result':{}},
             {'id':'Q2','name':'query_operations','args':{},'result':{}}]
    with scope() as session:
        p=session.get(Plan,'TESTAPI')
        r=report();r['claims'][0]['evidence_ids']=['INVENTED']
        with pytest.raises(ValueError):weekly._finish(session,p,r,queries)
        r=report();r['questions'][0]['text']='Understand the demand changes'
        assert weekly._finish(session,p,r,queries)['questions'][0]['text']==r['questions'][0]['text']
        r=report();r['questions'][0]['text']='Local context';r['report']='Demand changed.'
        assert weekly._finish(session,p,r,queries)['report']=='Demand changed.'
        r=report();r['questions']=[]
        assert weekly._finish(session,p,r,queries)['questions']==[]
        with pytest.raises(ValueError):weekly._finish(session,p,report(),[])
        r=report();r.pop('presentation')
        with pytest.raises(ValueError):weekly._finish(session,p,r,queries)

def test_offline_is_honest_and_does_not_close_original_questions(api,monkeypatch):
    c,_,_,_=api
    before=c.get('/api/plans/TESTAPI').json()['discussion']
    monkeypatch.setattr(chat,'provider_info',lambda:{'live':False})
    assert c.post('/api/plans/TESTAPI/review').json()['status']=='offline'
    assert c.get('/api/plans/TESTAPI').json()['discussion']==before

def test_provider_failure_keeps_query_trace(api,monkeypatch):
    from scoop.ai import exploration_tools
    _,scope,_,_=api
    monkeypatch.setattr(exploration_tools,'execute',lambda *a:{'units':20})
    count=0
    def wire(payload):
        nonlocal count
        count+=1
        if count==1:return {'candidates':[{'content':{'role':'model','parts':[{'functionCall':{'name':'catalog_groups','args':{}}}]}}]}
        raise gemini.ProviderUnavailable('fixture_timeout')
    with scope() as session:
        result=weekly.investigate(session,session.get(Plan,'TESTAPI'),wire)
        assert result['status']=='failed' and len(result['queries'])==2


def _legacy(scope):
    legacy=report();legacy.pop('presentation')
    legacy.update(status='complete',model='original-model',usage={'input_tokens':100,'output_tokens':50},created_at='saved-date',
                  queries=[{'id':'Q1','name':'query_group','args':{'group_ids':['a','b']},
                            'result':{'recent':{'requested_units':20},'daily':[{'date':'2026-07-05','requested_units':20}],
                                      'cusum':{'checks':[{'up':0}],'series':[{'date':'2026-07-05','up':0}]}}}])
    discussion={'items':[{'id':'USER-TOPIC','title':'Keep this unresolved context','status':'open','finding_id':None,
                          'note':'Discussed with the planner','managed':True,'review_seed':True},
                         {'id':'CLOSED-TOPIC','title':'Already understood','status':'resolved','finding_id':None,
                          'note':'Useful answer saved','managed':True}]}
    with scope() as session:
        p=session.get(Plan,'TESTAPI');p.summary={**p.summary,'weekly_review':legacy,'discussion':discussion}
        session.add(ChatMessage(plan_id=p.id,stage='discover',role='user',content='Keep our conversation.',meta={},created_at=p.created_at))
    return deepcopy(legacy),deepcopy(discussion)


def test_explicit_legacy_upgrade_uses_saved_evidence_once_and_preserves_history(api,monkeypatch):
    from scoop.ai import exploration_tools
    c,scope,_,_=api
    legacy,discussion=_legacy(scope)
    monkeypatch.setattr(exploration_tools,'execute',lambda *args:pytest.fail('A legacy design upgrade must not rerun queries'))
    calls=[]
    def wire(payload):
        calls.append(deepcopy(payload))
        declaration=payload['tools'][0]['functionDeclarations']
        assert len(declaration)==1 and declaration[0]['name']=='finish_report_presentation'
        context=json.loads(payload['contents'][0]['parts'][0]['text'])
        assert context['saved_report']['report']==legacy['report']
        assert context['saved_evidence'][0]['result']['daily']
        assert 'series' not in context['saved_evidence'][0]['result']['cusum']
        return {'modelVersion':'designer-fixture','usageMetadata':{'promptTokenCount':20,'candidatesTokenCount':30},
                'candidates':[{'content':{'parts':[{'functionCall':{'name':'finish_report_presentation','args':presentation()}}]}}]}
    monkeypatch.setattr(gemini,'_wire',wire)
    monkeypatch.setattr(chat,'provider_info',lambda:{'live':True})
    before=c.get('/api/plans/TESTAPI').json()
    assert not calls and before['review']==legacy
    response=c.post('/api/plans/TESTAPI/review').json()
    assert response['status']=='complete' and response['presentation']==presentation()
    for key in legacy:assert response[key]==legacy[key]
    assert response['presentation_upgrade']['model']=='designer-fixture'
    after=c.get('/api/plans/TESTAPI').json()
    for key in ('discussion','messages','orders','directions','questions','decisions','watch'):
        assert after[key]==before[key],key
    with scope() as session:assert session.get(Plan,'TESTAPI').summary['discussion']==discussion
    assert c.post('/api/plans/TESTAPI/review').json()==response
    assert len(calls)==1


@pytest.mark.parametrize('failure',['provider','invalid_evidence'])
def test_legacy_upgrade_failure_retains_original_report_and_managed_items(api,monkeypatch,failure):
    c,scope,_,_=api
    legacy,discussion=_legacy(scope)
    def wire(payload):
        if failure=='provider':raise gemini.ProviderUnavailable('fixture_timeout')
        return {'candidates':[{'content':{'parts':[{'functionCall':{'name':'finish_report_presentation','args':presentation('INVENTED')}}]}}]}
    monkeypatch.setattr(gemini,'_wire',wire)
    monkeypatch.setattr(chat,'provider_info',lambda:{'live':True})
    before=c.get('/api/plans/TESTAPI').json()
    result=c.post('/api/plans/TESTAPI/review').json()
    assert result['status']=='complete' and 'presentation' not in result
    assert result['presentation_error'] and result['presentation_upgrade']['status']=='failed'
    for key in legacy:assert result[key]==legacy[key]
    after=c.get('/api/plans/TESTAPI').json()
    for key in ('discussion','messages','orders','directions','questions','decisions'):
        assert after[key]==before[key]
    with scope() as session:assert session.get(Plan,'TESTAPI').summary['discussion']==discussion


def test_compact_context_does_not_discard_saved_trace(api,monkeypatch):
    from scoop.ai import exploration_tools
    _,scope,_,_=api
    full={'groups':[{'id':'a','skus':['A'],'members':[{'sku':'A','name':'Product A'}]}],
          'daily':[{'date':'2026-07-05','requested_units':20}],
          'cusum':{'checks':[{'up':2}],'series':[{'date':'2026-07-05','up':2}]}}
    monkeypatch.setattr(exploration_tools,'execute',lambda *args:deepcopy(full))
    count=0
    def wire(payload):
        nonlocal count
        count+=1
        if count==1:
            return {'candidates':[{'content':{'role':'model','parts':[
                {'functionCall':{'name':'query_group','args':{'group_ids':['a','b']}}},
                {'functionCall':{'name':'query_operations','args':{'group_ids':['a','b']}}}]}}]}
        response=payload['contents'][-1]['parts'][0]['functionResponse']['response']
        assert 'members' not in response['groups'][0]
        assert response['daily'] and response['cusum']['checks']
        assert 'series' not in response['cusum']
        return {'candidates':[{'content':{'parts':[{'functionCall':{'name':'finish_weekly_review','args':report()}}]}}]}
    with scope() as session:
        result=weekly.investigate(session,session.get(Plan,'TESTAPI'),wire)
        assert result['status']=='complete' and result['queries'][0]['result']==full


@pytest.mark.parametrize('fragment,css',[
    ('<script>alert(1)</script>',''),
    ('<p onclick="alert(1)">Demand changed</p>',''),
    ('<a href="https://example.com">Evidence</a>',''),
    ('<p>Demand changed</p>','@import "https://example.com/report.css";'),
    ('<p>Demand changed</p>','p { background: url(https://example.com/image.png) }'),
])
def test_visual_transport_blocks_code_and_network_without_rewriting_prose(api,fragment,css):
    _,scope,_,_=api
    queries=[{'id':'Q1','name':'query_group','args':{'group_ids':['a','b']},'result':{}},
             {'id':'Q2','name':'query_operations','args':{},'result':{}}]
    with scope() as session:
        r=report();r['presentation'].update(html=fragment,css=css)
        with pytest.raises(ValueError):weekly._finish(session,session.get(Plan,'TESTAPI'),r,queries)
