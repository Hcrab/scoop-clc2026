"""Watch continuity/review regressions run entirely in disposable schemas."""
from datetime import date,datetime
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import select,func
from test_api_state import api
from scoop.models import Plan,WatchItem,Decision,PurchaseSuggestion,DirectionItem,NodeInventory
from scoop import workflow

def test_review_idempotent_and_strategy_combines_approval(api):
    c,scope,_,_=api
    detail=c.get('/api/plans/TESTAPI').json()
    assert detail['watch_review']['confirmed'] is False
    baseline=[w for w in detail['watch'] if w['origin']=='baseline']
    assert len(baseline)==5
    assert {'below_lead','excess','projected'} <= {w['scope'].get('mode') for w in baseline}
    def approve(): return c.post('/api/plans/TESTAPI/watch-review',json={'confirmed':True}).status_code
    with ThreadPoolExecutor(max_workers=2) as executor: assert list(executor.map(lambda _:approve(),range(2)))==[200,200]
    with scope() as s:
        assert s.scalar(select(func.count()).select_from(Decision).where(Decision.key=='watch_review'))==1
        assert workflow.review_state(s,s.get(Plan,'TESTAPI'))['confirmed']
    assert c.post('/api/plans/TESTAPI/watch-review',json={'confirmed':False}).status_code==422
    assert c.post('/api/plans/TESTAPI/questions/TESTAPI-Q',json={'answer':'persistent'}).status_code==200
    assert c.get('/api/plans/TESTAPI').json()['watch_review']['confirmed'] is False
    assert c.post('/api/plans/TESTAPI/advance').json()['stage']=='direction'
    assert c.post('/api/plans/TESTAPI/advance').json()['stage']=='execute'
    with scope() as s:
        info=workflow.state(s.get(Plan,'TESTAPI'))
        assert info['review']['confirmed'] is True
        assert info['approved_projection']['capacity_pallets']==10
        snapshot=info['approved_review']['items']
        old_watch=snapshot[0]
    assert c.put('/api/plans/TESTAPI/watch/'+old_watch['id'],json={'title':'Midweek separate revision'}).status_code==200
    with scope() as s: assert workflow.state(s.get(Plan,'TESTAPI'))['approved_review']['items'][0]['title']==old_watch['title']
    detail=c.get('/api/plans/TESTAPI').json()
    assert detail['watch_review']['confirmed'] is True
    assert next(w for w in detail['watch_review']['items'] if w['id']==old_watch['id'])['title']==old_watch['title']
    assert next(w for w in detail['watch'] if w['id']==old_watch['id'])['title']=='Midweek separate revision'
    assert c.delete('/api/plans/TESTAPI/watch/'+old_watch['id']).status_code==200
    detail=c.get('/api/plans/TESTAPI').json()
    assert old_watch['id'] not in {w['id'] for w in detail['watch']}
    assert old_watch['id'] in {w['id'] for w in detail['watch_review']['items']}

    assert c.put('/api/plans/TESTAPI/directions/TESTAPI-D',json={'bucket':'more','factor':1.2,'districts':['Kowloon']}).status_code==409

def test_custom_edits_archives_and_invalid_scope_rollback(api):
    c,scope,_,_=api
    detail=c.get('/api/plans/TESTAPI').json()
    watch=next(w for w in detail['watch'] if w['kind']=='tag_share')
    body={'kind':'tag_share','title':'My focused assumption','assumption':'Do customers continue choosing fruit?','scope':{'tag_id':'family:fruit','districts':['Kowloon']}}
    assert c.put('/api/plans/TESTAPI/watch/'+watch['id'],json=body).status_code==200
    bad={**body,'title':'Should not persist','scope':{'districts':[{'not':'a district'}]}}
    assert c.put('/api/plans/TESTAPI/watch/'+watch['id'],json=bad).status_code==422
    with scope() as s:
        p=s.get(Plan,'TESTAPI');workflow.refresh_generated(s,p)
        assert s.get(WatchItem,watch['id']).title==body['title']
        assert s.get(WatchItem,watch['id']).scope==body['scope']
    assert c.delete('/api/plans/TESTAPI/watch/'+watch['id']).status_code==200
    for _ in range(2):
        with scope() as s: workflow.refresh_generated(s,s.get(Plan,'TESTAPI'))
        assert watch['id'] not in {w['id'] for w in c.get('/api/plans/TESTAPI').json()['watch']}
    with scope() as s: assert s.get(WatchItem,watch['id']).status=='archived'
    assert c.put('/api/plans/TESTAPI/watch/'+watch['id'],json=body).status_code==409

def test_carryover_reopen_and_recap_never_leaks_future(api):
    c,scope,_,_=api
    # Initialize previous plan once, then preserve its reviewed historical choices.
    c.get('/api/plans/TESTAPI')
    custom={'kind':'tag_share','title':'Follow fruit two weeks','assumption':'Still unresolved','scope':{'tag_id':'family:fruit','districts':['Kowloon']}}
    wid=c.post('/api/plans/TESTAPI/watch',json=custom).json()['id']
    archived=c.post('/api/plans/TESTAPI/watch',json={**custom,'title':'Already finished'}).json()['id']
    c.delete('/api/plans/TESTAPI/watch/'+archived)
    with scope() as s:
        previous=s.get(Plan,'TESTAPI');previous.stage='execute'
        suggestion=s.get(PurchaseSuggestion,('TESTAPI','IC001'));suggestion.status='confirmed';suggestion.final_cases=3
        s.add(Plan(id='NEXTAPI',week_start=date(2026,7,13),stage='discover',goal='margin',created_at=datetime.now(),summary={}))
    first=c.get('/api/plans/NEXTAPI').json();second=c.get('/api/plans/NEXTAPI').json()
    carried=next(w for w in first['watch'] if w['title']==custom['title'])
    assert carried['carried_from']=='TESTAPI'
    assert [w['id'] for w in first['watch']]==[w['id'] for w in second['watch']]
    assert 'Already finished' not in {w['title'] for w in first['watch']}
    recap=first['recap']
    assert recap['facts_through']=='2026-07-12'
    assert (recap['ordered_units'],recap['shipped_units'])==(10,10)
    assert recap['confirmed_orders']==1 and recap['confirmed_cases']==3
    assert 'no causal improvement' in recap['provenance']
    assert all(point['date']<'2026-07-13' for watch in first['watch'] for point in watch['series'])
    c.delete('/api/plans/NEXTAPI/watch/'+carried['id'])
    assert carried['id'] not in {w['id'] for w in c.get('/api/plans/NEXTAPI').json()['watch']}
    with scope() as s:
        assert s.get(WatchItem,wid).status=='active'
        assert s.get(WatchItem,wid).assumption=='Still unresolved'

def test_watch_missing_interval_is_review_and_read_is_fresh(api):
    c,scope,_,_=api
    body={'kind':'tag_share','title':'No calibrated bounds','scope':{'tag_id':'family:fruit'},'assumption':'Check'}
    wid=c.post('/api/plans/TESTAPI/watch',json=body).json()['id']
    watch=next(w for w in c.get('/api/plans/TESTAPI').json()['watch'] if w['id']==wid)
    assert watch['state']=='review'
    assert watch['expected_low'] is None and watch['expected_high'] is None
    with scope() as s: s.get(NodeInventory,(date(2026,7,12),'IC001')).on_hand_units=1
    assert next(w for w in c.get('/api/plans/TESTAPI').json()['watch'] if w['scope'].get('mode')=='below_lead')['value']==1
    with scope() as s: s.get(NodeInventory,(date(2026,7,12),'IC001')).on_hand_units=100
    assert next(w for w in c.get('/api/plans/TESTAPI').json()['watch'] if w['scope'].get('mode')=='below_lead')['value']==0

def test_concurrent_watch_create_uses_one_identity(api):
    c,scope,_,_=api
    body={'kind':'fill_rate','title':'Concurrent user choice','assumption':'Keep once','scope':{}}
    with ThreadPoolExecutor(max_workers=2) as executor:
        result=list(executor.map(lambda _:c.post('/api/plans/TESTAPI/watch',json=body),range(2)))
    assert all(r.status_code==200 for r in result)
    assert result[0].json()['id']==result[1].json()['id']
    with scope() as s: assert s.scalar(select(func.count()).select_from(WatchItem).where(WatchItem.title==body['title']))==1

def test_watch_batch_reads_shared_facts_once_and_closed_stage_rejects_changes(api):
    from sqlalchemy import event
    from scoop.api.watches import WatchData
    c,scope,_,_=api
    count=[]
    with scope() as s:
        engine=s.get_bind()
        def executed(*args): count.append(1)
        event.listen(engine,'before_cursor_execute',executed)
        try:
            data=WatchData(s,date(2026,7,13),lambda *args:[])
            initial=len(count)
            plan=s.get(Plan,'TESTAPI')
            initial=len(count)
            for i in range(20):
                w=WatchItem(id='batch'+str(i),plan_id=plan.id,kind='tag_share',title='Batch',assumption='',scope={'tag_id':'family:fruit'},origin='user',status='active')
                view=data.view(w,plan)
                assert view['state']=='review'
                assert all(point['date']<'2026-07-13' for point in view['series'])
            assert len(count)==initial
        finally: event.remove(engine,'before_cursor_execute',executed)
        plan.stage='closed'
    assert c.post('/api/plans/TESTAPI/watch-review',json={'confirmed':True}).status_code==409
    assert c.post('/api/plans/TESTAPI/watch',json={'kind':'fill_rate','title':'Cannot add','scope':{}}).status_code==409

def test_partial_edit_and_bad_mode_do_not_change_reviewed_choice(api):
    c,scope,_,_=api
    wid=c.post('/api/plans/TESTAPI/watch',json={'kind':'fill_rate','title':'Original','scope':{}}).json()['id']
    assert c.put('/api/plans/TESTAPI/watch/'+wid,json={'title':'Renamed'}).status_code==200
    assert c.put('/api/plans/TESTAPI/watch/'+wid,json={'kind':'days_cover','scope':{'mode':[]}}).status_code==422
    assert c.put('/api/plans/TESTAPI/watch/'+wid,json={'title':None}).status_code==422
    with scope() as s:
        w=s.get(WatchItem,wid)
        assert w.title=='Renamed' and w.kind=='fill_rate' and w.scope=={}
