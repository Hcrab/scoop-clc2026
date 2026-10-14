"""Persisted advisory topics with disposable schemas and no provider requests."""
from datetime import date, datetime
import json

import pytest
from pydantic import ValidationError

from test_api_state import api
from scoop.ai import gemini, tools
from scoop.models import Plan, Question, Finding
from scoop.discussion import view


def test_open_topics_do_not_block_advance_or_answer_questions(api):
    client, scope, _, _=api
    agenda=client.get('/api/plans/TESTAPI').json()['discussion']
    assert agenda['open_count']==1
    assert set(agenda['items'][0])=={'id','title','status','finding_id','note'}
    assert client.post('/api/plans/TESTAPI/advance').json()['stage']=='direction'
    assert client.get('/api/plans/TESTAPI').json()['discussion']==agenda
    with scope() as session:
        assert session.get(Question,'TESTAPI-Q').answer is None
        assert session.get(Plan,'TESTAPI').summary['discussion']['items'][0]['status']=='open'


def test_managed_seed_stays_closed_and_reopens_explicitly(api):
    client, scope, _, _=api
    topic=client.get('/api/plans/TESTAPI').json()['discussion']['items'][0]
    with scope() as session:
        plan=session.get(Plan,'TESTAPI')
        tools.execute('update_discussion',{'operation':'resolve','topic_id':topic['id'],'note':'Evidence explained.'},session,plan,'discover')
        tools.execute('update_discussion',{'operation':'resolve','topic_id':topic['id'],'note':'Evidence explained.'},session,plan,'discover')
    assert client.get('/api/plans/TESTAPI').json()['discussion']['open_count']==0
    with scope() as session:
        plan=session.get(Plan,'TESTAPI')
        assert session.get(Question,'TESTAPI-Q').answer is None
        tools.execute('update_discussion',{'operation':'reopen','topic_id':topic['id'],'note':'Cause still uncertain.'},session,plan,'discover')
    assert client.get('/api/plans/TESTAPI').json()['discussion']['open_count']==1


def test_duplicate_adds_and_foreign_ids_cannot_cross_plans(api):
    _, scope, _, _=api
    with scope() as session:
        other=Plan(id='OTHER',week_start=date(2026,6,29),stage='execute',goal='margin',created_at=datetime.now(),summary={})
        session.add(other);session.flush()
        plan=session.get(Plan,'TESTAPI')
        args={'operation':'add','title':'Check heat next week','finding_id':'TESTAPI-F','note':'Follow up'}
        first,_=tools.execute('update_discussion',args,session,plan,'discover')
        second,_=tools.execute('update_discussion',args,session,plan,'discover')
        assert first==second and len(second['discussion']['items'])==2
        with pytest.raises(ValueError,match='current plan'):
            tools.execute('update_discussion',args,session,other,'execute')
        topic=first['discussion']['items'][-1]['id']
        with pytest.raises(ValueError,match='current plan'):
            tools.execute('update_discussion',{'operation':'resolve','topic_id':topic},session,other,'execute')
        assert view(session,other)=={'open_count':0,'items':[]}
        with pytest.raises(ValidationError):
            tools.execute('update_discussion',{'operation':'add','title':'x'*161},session,plan,'discover')
        with pytest.raises(ValidationError):
            tools.execute('update_discussion',{'operation':'add','title':'Heat','note':'x'*2001},session,plan,'discover')


def test_answered_seeds_and_offline_classification_resolve(api):
    client, scope, _, _=api
    with scope() as session:session.get(Question,'TESTAPI-Q').answer='weather'
    assert client.get('/api/plans/TESTAPI').json()['discussion']['open_count']==0
    with scope() as session:
        session.get(Question,'TESTAPI-Q').answer=None
        session.get(Plan,'TESTAPI').summary={}
    result=client.post('/api/plans/TESTAPI/chat',json={'message':'Record this as persistent','stage':'discover','context':{'finding_id':'TESTAPI-F'}}).json()
    assert result['discussion']['open_count']==0
    assert result['actions'][0]['type']=='classification'


def test_informational_model_agenda_edit_preserves_business_and_stream_contract(api,monkeypatch):
    from scoop.ai import http
    client, _, _, _=api
    before=client.get('/api/plans/TESTAPI').json()
    topic=before['discussion']['items'][0]['id']
    count=0
    def wire(payload):
        nonlocal count
        count+=1
        if count==1:
            declarations=payload['tools'][0]['functionDeclarations']
            assert any(d['name']=='update_discussion' for d in declarations)
            assert not any(d['name'] in tools.MUTATING for d in declarations)
            return {'candidates':[{'content':{'parts':[{'functionCall':{'name':'update_discussion','args':{'operation':'resolve','topic_id':topic,'note':'Demand evidence explained; cause remains uncertain.'}}}]}}]}
        return {'candidates':[{'content':{'parts':[{'text':'The evidence compares demand with expectations; it does not establish the cause.'}]}}]}
    monkeypatch.setattr(gemini,'_wire',wire)
    monkeypatch.setattr(http,'respond',gemini.respond)
    response=client.post('/api/plans/TESTAPI/chat/stream',json={'message':'Explain this finding','stage':'discover'})
    block=next(b for b in response.text.split('\n\n') if b.startswith('event: result'))
    result=json.loads(block.split('data: ',1)[1])
    assert result['discussion']['open_count']==0
    after=client.get('/api/plans/TESTAPI').json()
    for key in ('directions','orders','questions','decisions'):
        assert after[key]==before[key]
    assert after['plan']['goal']==before['plan']['goal']
    assert after['plan']['stage']==before['plan']['stage']
    with pytest.raises(ValidationError):
        tools.DiscussionArgs.model_validate({'operation':'add','title':'Topic','goal':'sales'})
