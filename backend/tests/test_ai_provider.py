"""Provider failures, intent boundaries and real tool execution without network."""
from dataclasses import replace
import json
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi import HTTPException
from sqlalchemy import func,select
from test_api_state import api
from scoop.ai import gemini,tools,usage,chat
from scoop.models import Plan,Decision,WatchItem


def response(*parts):
    return {'candidates':[{'content':{'role':'model','parts':list(parts)}}],
            'usageMetadata':{'promptTokenCount':100,'candidatesTokenCount':20,'thoughtsTokenCount':5}}


@pytest.mark.parametrize('message',[
    '请告诉我怎么增加水果冰的采购量',
    'Should I reduce the order?',
    'Set a target in your example, but do not change the plan',
    '先给建议，不要直接改。',
    '如果我把目标改为满足率会怎样？',
    '可以增加港岛的补货吗？',
])
def test_information_requests_cannot_mutate(message):
    assert not gemini._may_mutate(message)


@pytest.mark.parametrize('message',['请把目标设为满足率 98%','Record this as a persistent change','帮我盯住港岛水果类缺货'])
def test_explicit_changes_are_available(message):
    assert gemini._may_mutate(message)


def test_model_mutation_attempt_on_readonly_request_is_rejected(api,monkeypatch):
    _,scope,_,_=api
    calls=[]
    def wire(payload):
        calls.append(payload)
        if len(calls)==1:
            return response({'functionCall':{'name':'set_goal','args':{'goal':'sales'}}})
        assert 'no change was authorized' in payload['contents'][-1]['parts'][0]['functionResponse']['response']['error']
        return response({'text':'No change was made.'})
    monkeypatch.setattr(gemini,'_wire',wire)
    with scope() as s:
        plan=s.get(Plan,'TESTAPI')
        answer=gemini.respond(s,plan,'Why should I change the goal?','discover')
        assert plan.goal=='margin' and answer.actions==[]
        assert not any(d['name'] in tools.MUTATING for d in calls[0]['tools'][0]['functionDeclarations'])


def test_successful_mutation_survives_explanation_outage_without_repeat(api,monkeypatch):
    _,scope,_,_=api
    from scoop.ai import exploration_tools
    from scoop.algorithms.groups import Group
    monkeypatch.setattr(exploration_tools,'_groups',lambda _: {'family:fruit':Group('family:fruit','Fruit','family',('IC001',))})
    count=0
    def wire(payload):
        nonlocal count
        count+=1
        if count==1:return response({'functionCall':{'name':'set_override','args':{'cohort':'COHORT-FRUIT','type':'ends_on','value':'2026-08-10','note':'Summer one-off'}}})
        raise gemini.ProviderUnavailable('connection_unavailable')
    monkeypatch.setattr(gemini,'_wire',wire)
    with scope() as s:
        plan=s.get(Plan,'TESTAPI')
        plan.summary={'cohort_model':{'leaves':[{'id':'COHORT-FRUIT','tag_path':[{'id':'family:fruit','included':True}],'districts':['Kowloon'],'skus':['IC001']}]}}
        answer=gemini.respond(s,plan,'The fruit group ends on 10 Aug; record that','discover')
        assert len(answer.actions)==1
        assert answer.actions[0]['type']=='edit'
        assert answer.actions[0]['edit_id']
        assert answer.fallback_reason=='connection_unavailable'
        assert answer.tool_trace[0]['status']=='ok'
        assert s.scalar(select(func.count()).select_from(Decision))==1

def test_excess_tool_calls_receive_explicit_protocol_responses(api,monkeypatch):
    _,scope,_,_=api
    payloads=[];executed=[]
    def wire(payload):
        payloads.append(payload)
        if len(payloads)==1:
            return response(*[{'functionCall':{'name':'inspect_order','id':str(i),'args':{'sku':str(i)}}} for i in range(5)])
        replies=payload['contents'][-1]['parts']
        assert len(replies)==5
        assert replies[-1]['functionResponse']['id']=='4'
        assert 'four tools' in replies[-1]['functionResponse']['response']['error']
        return response({'text':'Four records checked; the fifth needs another batch.'})
    monkeypatch.setattr(gemini,'_wire',wire)
    monkeypatch.setattr(tools,'execute',lambda name,args,*rest:(executed.append(args['sku']) or {'ok':True},None))
    with scope() as s:
        result=gemini.respond(s,s.get(Plan,'TESTAPI'),'Compare these products','discover')
    assert executed==['0','1','2','3']
    assert result.tool_trace[-1]['status']=='error'


def test_stage_and_scope_enforced_even_when_model_requests_invalid_change(api):
    _,scope,_,_=api
    with scope() as s:
        plan=s.get(Plan,'TESTAPI');plan.stage='execute';s.flush()
        result,action=tools.execute('set_goal',{'goal':'sales'},s,plan,'execute')
        assert action['type']=='edit' and plan.stage=='direction'
        watch_count=s.scalar(select(func.count()).select_from(WatchItem))
        with pytest.raises(ValueError,match='current plan'):
            tools.execute('inspect_finding',{'finding_id':'ANOTHERPLAN-F'},s,plan,'execute')
        with pytest.raises(ValueError,match='districts'):
            tools.execute('add_watch',{'kind':'fill_rate','title':'Bad district','assumption':'Test','districts':['Unknown']},s,plan,'execute')
        assert s.scalar(select(func.count()).select_from(WatchItem))==watch_count


def test_failed_provider_uses_honest_scripted_fallback(api,monkeypatch):
    _,scope,_,_=api
    monkeypatch.setattr(chat,'settings',replace(chat.settings,llm_provider='gemini'))
    monkeypatch.setenv('GEMINI_API_KEY','fixture-only')
    monkeypatch.setattr(gemini,'_wire',lambda _:(_ for _ in ()).throw(gemini.ProviderUnavailable('provider_http_429')))
    with scope() as s:
        answer=chat.respond(s,s.get(Plan,'TESTAPI'),'Why did fruit rise?','discover')
        assert answer.provider=='scripted'
        assert 'live assistant is unavailable' in answer.reply
        assert answer.fallback_reason=='provider_http_429'
        assert 'fixture-only' not in answer.reply


def test_argon_allowance_counts_reasoning_at_selected_model_rate(tmp_path):
    ledger=tmp_path/'argon.sqlite3'
    rid=usage.reserve('gemini-4-argon','fixture',1000,8192,path=ledger)
    assert usage.summary(path=ledger)['estimated_usd']==pytest.approx(.16784)
    usage.finish(rid,{'promptTokenCount':1000,'candidatesTokenCount':200,'thoughtsTokenCount':300},path=ledger)
    assert usage.summary(path=ledger)['estimated_usd']==pytest.approx(.014)


def test_usage_reservation_is_atomic_and_unknown_outcome_keeps_reservation(tmp_path,monkeypatch):
    ledger=tmp_path/'usage.sqlite3'
    monkeypatch.setattr(usage,'settings',replace(usage.settings,llm_budget_usd=1,llm_max_calls=1))
    def reserve_one(_):
        try:return usage.reserve('fixture','hash',100,100,path=ledger)
        except usage.UsageLimit:return None
    with ThreadPoolExecutor(max_workers=2) as pool:ids=list(pool.map(reserve_one,range(2)))
    assert sum(rid is not None for rid in ids)==1
    before=usage.summary(path=ledger)
    usage.finish(next(rid for rid in ids if rid),{},'transport_error',path=ledger)
    assert usage.summary(path=ledger)['estimated_usd']==before['estimated_usd']>0


def test_ledger_counts_thinking_tokens_and_contains_no_prompt_or_key(tmp_path):
    ledger=tmp_path/'usage.sqlite3'
    rid=usage.reserve('fixture','digest-only',1000,1000,path=ledger)
    usage.finish(rid,{'promptTokenCount':200,'candidatesTokenCount':30,'thoughtsTokenCount':70},path=ledger)
    stats=usage.summary(path=ledger)
    assert stats['input_tokens']==200 and stats['output_tokens']==100
    with usage.ledger(ledger) as db:
        columns={r[1] for r in db.execute('PRAGMA table_info(calls)')}
    assert not ({'key','prompt','message','api_key'} & columns)


def test_stream_saves_response_and_exposes_real_progress_only(api,monkeypatch):
    from scoop.ai import http
    c,scope,_,_=api
    def provider(session,plan,message,stage,focus,progress):
        progress({'phase':'tool','label':'Checking the evidence','tool':'inspect_finding'})
        return gemini.ChatReply('The check is complete.',provider='gemini',tool_trace=[{'name':'inspect_finding','status':'ok'}])
    monkeypatch.setattr(http,'respond',provider)
    response=c.post('/api/plans/TESTAPI/chat/stream',json={'message':'Explain this change','stage':'discover','context':{'finding_id':'TESTAPI-F'}})
    assert response.status_code==200
    assert response.headers['content-type'].startswith('text/event-stream')
    blocks=[block for block in response.text.split('\n\n') if block]
    assert blocks[0].startswith('event: progress') and blocks[1].startswith('event: result')
    result=json.loads(blocks[1].split('data: ',1)[1])
    assert result['discussion']==c.get('/api/plans/TESTAPI').json()['discussion']
    messages=c.get('/api/plans/TESTAPI').json()['messages']
    assert len(messages)==2 and messages[-1]['meta']['provider']=='gemini'
    assert messages[-1]['meta']['tool_trace'][0]['name']=='inspect_finding'


def test_stream_failure_rolls_back_partial_change_and_never_emits_success(api,monkeypatch):
    from scoop.ai import http
    c,scope,_,_=api
    def provider(session,plan,*args):
        plan.goal='sales';session.flush()
        raise ValueError('fixture failure after mutation')
    monkeypatch.setattr(http,'respond',provider)
    response=c.post('/api/plans/TESTAPI/chat/stream',json={'message':'Set sales goal','stage':'discover'})
    assert 'event: error' in response.text and 'event: result' not in response.text
    detail=c.get('/api/plans/TESTAPI').json()
    assert detail['plan']['goal']=='margin' and detail['messages']==[]


def test_chat_rejects_foreign_focus_and_blank_message(api):
    c,_,_,_=api
    for endpoint in ['chat','chat/stream']:
        assert c.post('/api/plans/TESTAPI/'+endpoint,json={'message':'  ','stage':'discover'}).status_code==422
    response=c.post('/api/plans/TESTAPI/chat',json={'message':'Explain this','stage':'discover','context':{'finding_id':'ANOTHER-F'}})
    assert response.status_code==422


def test_scripted_fallback_respects_no_change_and_chinese_watch_scope(api):
    c,scope,_,_=api
    before=c.get('/api/plans/TESTAPI').json()
    c.post('/api/plans/TESTAPI/chat',json={'message':'Can I watch fruit? Do not change the plan.','stage':'discover'})
    after=c.get('/api/plans/TESTAPI').json()
    assert len(after['watch'])==len(before['watch']) and len(after['decisions'])==len(before['decisions'])
    answer=c.post('/api/plans/TESTAPI/chat',json={'message':'帮我盯住九龙水果类的缺货','stage':'discover'}).json()
    assert answer['actions'][0]['type']=='watch'
    created=next(w for w in c.get('/api/plans/TESTAPI').json()['watch'] if w['id']==answer['actions'][0]['id'])
    assert created['scope']=={'tag_id':'family:fruit','districts':['Kowloon']}


@pytest.mark.parametrize('message',[
    "Don't add a fruit fill rate watch in Kowloon.",
    'Do not monitor fruit shortages in HK Island.',
    'Never increase fruit orders.',
    'Discuss fruit without adding a watch.',
    '不要监控港岛水果类缺货。',
    '先不盯住九龙水果类的缺货。',
])
def test_negated_requests_preserve_fallback_plan(api,message):
    c,_,_,_=api
    assert not gemini._may_mutate(message)
    before=c.get('/api/plans/TESTAPI').json()
    response=c.post('/api/plans/TESTAPI/chat',json={'message':message,'stage':'discover'})
    assert response.status_code==200 and response.json()['actions']==[]
    after=c.get('/api/plans/TESTAPI').json()
    assert after['watch']==before['watch']
    assert after['decisions']==before['decisions']
    assert after['plan']==before['plan']
