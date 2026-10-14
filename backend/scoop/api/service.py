"""Planner state and read-only views; all facts are cut off at the demo clock."""
from datetime import date, datetime, timedelta
import csv
import io
import json
import math
import hashlib
from pathlib import Path
from threading import Lock
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from typing import Literal
from sqlalchemy import select, text, delete

from ..db import session_scope, get_setting, set_setting
from ..config import ROOT, settings
from ..ai.chat import provider_info
from ..models import *

router = APIRouter(prefix='/api')
creation_lock = Lock()
STAGES = ['discover', 'direction', 'execute']
MIN_DAY, MAX_DAY = date(2026, 6, 1), date(2026, 8, 31)
PROVENANCE = 'Synthetic historical stock at the end of yesterday. Confirmed demo orders are recorded, not physically applied to this historical simulation.'

def clean(value):
    if isinstance(value, dict): return {k: clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [clean(v) for v in value]
    if isinstance(value, (date, datetime)): return value.isoformat()
    if hasattr(value, 'item'): return clean(value.item())
    if isinstance(value, float) and not math.isfinite(value): return None
    return value

def row(obj):
    return clean({c.name: getattr(obj, c.name) for c in obj.__table__.columns})

def today(): return date.fromisoformat(get_setting('today', '2026-07-13'))

def query(s, sql, **params): return [dict(r) for r in s.execute(text(sql), params).mappings()]

def plan_for(s, pid, stage=None):
    p = s.scalar(select(Plan).where(Plan.id == pid).with_for_update()) if stage else s.get(Plan, pid)
    if not p: raise HTTPException(404, 'Plan not found')
    if p.week_start > today(): raise HTTPException(409, 'Plan is later than the demo clock; advance the clock to view its observed facts.')
    if stage and (p.stage not in stage or p.week_start > today()): raise HTTPException(409, 'This stage is read-only; switch to the current editable stage.')
    return p

def decision(s, p, key, value, source='ui'):
    s.add(Decision(plan_id=p.id, stage=p.stage, key=key, value=clean(value), source=source, created_at=datetime.now()))

def objects(s, cls, pid):
    # PostgreSQL row order changes after UPDATE; keep the visible cards stable.
    return s.scalars(select(cls).where(cls.plan_id == pid).order_by(*cls.__table__.primary_key.columns)).all()

def recompute(s, p):
    from ..planning import suggest_orders, reason_text
    directions = [row(d) for d in objects(s, DirectionItem, p.id)]
    from ..cohort_context import load_overrides
    try: orders = suggest_orders(p.week_start, directions, service_level=p.service_level, goal=p.goal, overrides=load_overrides(s, p.week_start))
    except Exception as exc: raise HTTPException(503, f'Forecast recomputation failed: {type(exc).__name__}: {exc}') from exc
    names = dict(s.execute(select(Product.sku, Product.name)).all())
    s.execute(delete(PurchaseSuggestion).where(PurchaseSuggestion.plan_id == p.id))
    for r in orders.itertuples():
        fields = {k: clean(getattr(r, k)) for k in ['sku', 'order_date', 'demand_p10', 'demand_p50', 'demand_p90', 'adjustment', 'critical_ratio', 'target_units', 'on_hand_units', 'on_order_units', 'inventory_position', 'suggested_cases', 'capacity_cut_cases']}
        s.add(PurchaseSuggestion(plan_id=p.id, protection_days=int(r.pdays), final_cases=int(r.final_cases) if r.sku in orders.attrs.get('cohort_model', {}).get('cases_overrides', {}) else None, status='suggested', reason=reason_text(r, names, directions), **fields))
    p.summary={**(p.summary or {}),'orders_due':int((orders.suggested_cases-orders.capacity_cut_cases>0).sum()),'goal':p.goal,
               'cohort_model':orders.attrs.get('cohort_model', {})}
    from .. import workflow
    refresh_watches(s,p)
    workflow.invalidate_review(p)

def catalog(s):
    suppliers = {x.id: x for x in s.scalars(select(Supplier))}
    nutrition = {x.sku: row(x) for x in s.scalars(select(ProductNutrition))}
    tags = query(s, 'SELECT pt.sku, t.id, t.name, t.dimension_id AS dimension, pt.value_num AS value FROM product_tags pt JOIN tags t ON t.id=pt.tag_id ORDER BY t.id')
    return [dict(row(p), supplier_name=suppliers[p.supplier_id].name, lead_time_days=suppliers[p.supplier_id].lead_time_days, order_weekday=suppliers[p.supplier_id].order_weekday, tags=[{k:v for k,v in t.items() if k != 'sku'} for t in tags if t['sku']==p.sku], nutrition=nutrition.get(p.sku, {})) for p in s.scalars(select(Product).order_by(Product.sku))]

def metrics(s, cutoff, store=None):
    data = query(s, 'SELECT COALESCE(SUM(ordered_units),0) AS ordered_units, COALESCE(SUM(shipped_units),0) AS shipped_units FROM store_orders WHERE date>=:start AND date<:end' + (' AND store_id=:store' if store else ''), start=cutoff-timedelta(days=7), end=cutoff, store=store)[0]
    data['fill_rate'] = data['shipped_units']/data['ordered_units'] if data['ordered_units'] else 0
    return data

def plan_metrics(s, cutoff):
    result=metrics(s,cutoff)
    result.update(query(s,'SELECT COALESCE(SUM(n.on_hand_units),0) AS on_hand_units, COALESCE(SUM(n.on_hand_units::float/(p.units_per_case*p.cases_per_pallet)),0) AS pallets_used FROM node_inventory n JOIN products p USING(sku) WHERE n.date=:day',day=cutoff-timedelta(days=1))[0])
    return result

def refresh_watches(s,p):
    from .. import workflow
    workflow.initialize_plan(s,p)
    workflow.refresh_generated(s,p)

def evaluation_data():
    path = settings.reports_dir / 'evaluation.json'
    return clean(json.loads(path.read_text(encoding='utf-8'))) if path.exists() else {'status':'pending'}

@router.get('/evaluation')
def evaluation(): return evaluation_data()

@router.get('/bootstrap')
def bootstrap():
    day = today()
    with session_scope() as s:
        m = metrics(s, day)
        m.update(query(s, 'SELECT COALESCE(SUM(n.on_hand_units),0) AS on_hand_units, COALESCE(SUM(n.on_hand_units::float / (p.units_per_case*p.cases_per_pallet)),0) AS pallets_used FROM node_inventory n JOIN products p USING(sku) WHERE n.date=:day', day=day-timedelta(days=1))[0])
        node = s.scalar(select(Node))
        return clean(dict(today=day, provider=provider_info()['provider'], synthetic=True, plans=[row(p) for p in s.scalars(select(Plan).where(Plan.week_start<=day).order_by(Plan.week_start.desc()))], stores=[row(x) for x in s.scalars(select(Store).order_by(Store.id))], products=catalog(s), node=row(node) if node else None, metrics=m, evaluation=evaluation_data() if (settings.reports_dir/'evaluation.json').exists() else None, metadata={'inventory_provenance':PROVENANCE,'facts_through':day-timedelta(days=1),'clock_range':[MIN_DAY,MAX_DAY],'week_switch':'Selecting a plan reads history; only explicit clock changes change the as-of date.'}))

@router.get('/stores/{sid}')
def store_detail(sid: str):
    with session_scope() as s:
        store = s.get(Store, sid)
        if not store: raise HTTPException(404, 'Store not found')
        cutoff=today()
        daily=query(s,'SELECT date, SUM(ordered_units) AS ordered_units, SUM(shipped_units) AS shipped_units FROM store_orders WHERE store_id=:sid AND date<:cutoff AND date>=:start GROUP BY date ORDER BY date',sid=sid,cutoff=cutoff,start=cutoff-timedelta(days=60))
        products=query(s,'SELECT p.sku,p.name,SUM(o.ordered_units) AS ordered_units,SUM(o.shipped_units) AS shipped_units FROM store_orders o JOIN products p USING(sku) WHERE o.store_id=:sid AND o.date<:cutoff AND o.date>=:start GROUP BY p.sku,p.name ORDER BY SUM(o.ordered_units) DESC',sid=sid,cutoff=cutoff,start=cutoff-timedelta(days=7))
        for p in products: p['fill_rate']=p['shipped_units']/p['ordered_units'] if p['ordered_units'] else 0
        return clean({'store':row(store),'metrics':metrics(s,cutoff,sid),'daily':daily,'products':products})

def group_skus(s, tag):
    if not tag: return []
    if s.get(Tag,tag): return list(s.scalars(select(ProductTag.sku).where(ProductTag.tag_id==tag)))
    parts=tag.split(':')
    if len(parts)!=3 or parts[0]!='band' or parts[1] not in {'dairy','sweetness','sugar_100ml','price_hkd'} or parts[2] not in {'0','1','2'}: raise HTTPException(422,'Unknown watch tag or attribute band')
    values=s.execute(select(ProductTag.sku,ProductTag.value_num).where(ProductTag.tag_id==parts[1]).order_by(ProductTag.value_num)).all()
    if not values: return []
    def quantile(q):
        index=(len(values)-1)*q; lo=math.floor(index); hi=math.ceil(index)
        return values[lo][1]+(values[hi][1]-values[lo][1])*(index-lo)
    low,high=quantile(1/3),quantile(2/3)
    return [sku for sku,value in values if (0 if value<=low else 1 if value<=high else 2)==int(parts[2])]

def scoped_facts(s, scope, cutoff):
    districts=scope.get('districts',[])
    tag=scope.get('tag_id',scope.get('group'))
    skus=scope.get('skus', [scope['sku']] if scope.get('sku') else [])
    if tag and tag.startswith('band:'): skus=group_skus(s,tag); tag=None
    # Parameters only; supported scope is never interpolated into SQL.
    return query(s, '''SELECT o.date,o.sku,o.ordered_units,o.shipped_units FROM store_orders o JOIN stores st ON st.id=o.store_id
        WHERE o.date>=:start AND o.date<:cutoff AND (:all_districts OR st.district=ANY(:districts))
        AND (:all_skus OR o.sku=ANY(:skus)) AND (CAST(:tag AS text) IS NULL OR EXISTS (SELECT 1 FROM product_tags pt WHERE pt.sku=o.sku AND pt.tag_id=:tag))''', start=cutoff-timedelta(days=28), cutoff=cutoff, all_districts=not districts,districts=districts,all_skus=not skus,skus=skus,tag=tag)

def watch_view(s, w, cutoff, projection=None, data=None):
    from .watches import WatchData
    plan=s.get(Plan,w.plan_id)
    data=data or WatchData(s,cutoff,lambda tag,districts,start,end:plan_series(plan,tag,districts,start,end))
    return clean(data.view(w,plan,projection))


def projection_for(s,p,orders=None):
    from .. import workflow
    approved=workflow.state(p).get('approved_projection')
    if p.stage in {'execute','closed'}: return approved
    from ..planning import confirmation_capacity
    if orders is None:
        orders=[row(o) for o in objects(s,PurchaseSuggestion,p.id)]
    cases={o['sku']:o.get('effective_cases',o['final_cases'] if o['final_cases'] is not None else max(0,o['suggested_cases']-o['capacity_cut_cases'])) for o in orders}
    return clean(confirmation_capacity(p.week_start,cases))

def cached_series(tag, districts, start, cutoff, model_version=None):
    """Keep saved evidence attached to the model that produced it."""
    from ..monitoring import historical_chart
    _,series=historical_chart(cutoff,model_version)
    if series.empty: return []
    import pandas as pd
    selected=series[(series['group']==tag)&series.district.isin(districts)&(series.date>=pd.Timestamp(start))&(series.date<pd.Timestamp(cutoff))]
    if selected.empty: return []
    return clean(selected.groupby('date').agg(actual_share=('actual_share','mean'),expected_share=('expected_share','mean'),s_up=('s_up','max'),s_down=('s_down','max')).reset_index().to_dict('records'))

def plan_series(p,tag,districts,start,cutoff,model_version=None):
    version=model_version or (p.summary or {}).get('model_run',{}).get('version')
    return cached_series(tag,districts,start,cutoff,version)

@router.get('/plans/{pid}')
def get_plan(pid:str):
    from ..discussion import view as discussion_view
    from .. import workflow
    from .watches import WatchData,recap
    with session_scope() as s:
        p=plan_for(s,pid); cutoff=min(today(),p.week_start+timedelta(days=7))
        workflow.initialize_plan(s,p)
        findings=[]
        for f in objects(s,Finding,pid):
            item=row(f)
            from ..ai.narrator import saved_explanation
            item['explanation']=saved_explanation(f)
            item['hypotheses']=[row(h) for h in s.scalars(select(Hypothesis).where(Hypothesis.finding_id==f.id))]
            item['series']=plan_series(p,f.tag_id,f.evidence.get('districts',f.district.split(', ')),p.week_start-timedelta(days=56),min(cutoff,p.week_start),f.evidence.get('model_version'))
            findings.append(item)
        questions=[]
        for q in objects(s,Question,pid):
            item=row(q); options=q.options if isinstance(q.options,dict) else {'options':q.options}
            if q.finding_id:
                from ..ai.narrator import question_for
                f=s.get(Finding,q.finding_id)
                if f:
                    item['text']=question_for({'display':f.evidence.get('display',f.tag_id),'districts':f.evidence.get('districts',f.district.split(', ')),'direction':f.direction,'classification':f.classification})['text']
            item['options']={'options':[{'id':o.get('id',o.get('value')),'label':o.get('label',o.get('value'))} for o in options.get('options',[])],'recommended':options.get('recommended','unsure')}; questions.append(item)
        orders=query(s,'SELECT ps.*, p.name,p.brand,p.units_per_case,p.moq_cases,s.name AS supplier_name FROM purchase_suggestions ps JOIN products p USING(sku) JOIN suppliers s ON s.id=p.supplier_id WHERE ps.plan_id=:pid ORDER BY ps.order_date,p.name',pid=pid)
        for order in orders: order['effective_cases']=order['final_cases'] if order['final_cases'] is not None else max(0,order['suggested_cases']-order['capacity_cut_cases'])
        watches=[w for w in objects(s,WatchItem,pid) if w.status=='active']
        projection=projection_for(s,p,orders) if any(w.scope.get('mode')=='projected' for w in watches) else None
        data=WatchData(s,cutoff,lambda tag,districts,start,end:plan_series(p,tag,districts,start,end))
        views=[watch_view(s,w,cutoff,projection,data) for w in watches]
        review={**workflow.review_state(s,p),'items':views}
        approved=workflow.state(p).get('approved_review')
        if p.stage=='execute' and approved is not None:
            # A midweek watch edit belongs to Execute. The approved Direction
            # record must keep the exact titles, assumptions and scopes approved.
            frozen=[WatchItem(**snapshot) for snapshot in approved.get('items',[])]
            review={'confirmed':True,'confirmed_at':approved.get('confirmed_at'),
                    'items':[data.view(w,p,workflow.state(p).get('approved_projection')) for w in frozen]}
        return clean({'raw_trends':(p.summary or {}).get('raw_trends'),'review':(p.summary or {}).get('weekly_review',{'status':'not_started','report':'','queries':[]}),'discussion':discussion_view(s,p),'plan':row(p),'assistant':provider_info(),'metrics':plan_metrics(s,p.week_start),'findings':findings,'questions':questions,'directions':[row(d) for d in objects(s,DirectionItem,pid)],'orders':orders,'watch':views,'watch_review':review,'recap':recap(s,p,today(),cached_series),'decisions':[row(x) for x in objects(s,Decision,pid)],'messages':[row(x) for x in s.scalars(select(ChatMessage).where(ChatMessage.plan_id==pid).order_by(ChatMessage.id))],'metadata':{'inventory_provenance':PROVENANCE,'facts_through':cutoff-timedelta(days=1)}})

class NewPlan(BaseModel): week_start: date
@router.post('/plans')
def create_plan(body:NewPlan):
    week=body.week_start
    if week.weekday()!=0 or not MIN_DAY<=week<=min(today(),MAX_DAY): raise HTTPException(422,'Select a supported Monday between 2026-06-01 and the demo clock.')
    with creation_lock:
        with session_scope() as s:
            existing=s.scalar(select(Plan).where(Plan.week_start==week))
            if existing: return {'id':existing.id}
        from ..planning import build_plan
        try:
            pid=build_plan(week)
            from .. import workflow
            with session_scope() as s: workflow.initialize_plan(s,s.get(Plan,pid))
            from ..ai.weekly import prepare
            prepare(pid)
            return {'id':pid}
        except Exception as exc: raise HTTPException(503,f'Plan generation failed: {type(exc).__name__}: {exc}') from exc

class Answer(BaseModel): answer:str

@router.post('/plans/{pid}/review')
def weekly_review(pid:str):
    from ..ai.weekly import run
    with session_scope() as s:
        p=plan_for(s,pid)
        return clean(run(s,p))

def record_interpretation(s,p,q,answer,source='question'):
    if q.stage!=p.stage: raise HTTPException(409,'Question stage is read-only')
    allowed={'persistent','one_off','data_issue','weather','unsure','watch','mirror'}
    if answer not in allowed: raise HTTPException(422,'Unsupported finding interpretation')
    from ..discussion import resolve_question
    resolve_question(s,p,q)
    if q.answer==answer:return False
    q.answer=answer;q.answered_at=datetime.now();label='unsure' if answer=='watch' else answer
    f=s.get(Finding,q.finding_id) if q.finding_id else None
    if f:
        f.classification=label
        original=f.evidence.get('original_explanation',f.explanation)
        f.evidence={**f.evidence,'original_explanation':original,'human_interpretation':label}
        f.explanation=f'Planner interpretation: {label.replace("_"," ")}. Observed evidence: {original}'
        for h in s.scalars(select(Hypothesis).where(Hypothesis.finding_id==f.id)):h.selected=h.label==label
        for d in objects(s,DirectionItem,p.id):
            if d.finding_id==f.id:
                d.bucket=('more' if f.direction=='up' else 'less') if label=='persistent' else 'hold'
                d.factor=(min(2.0,max(1.01,f.share_now/max(f.share_before,1e-6))) if f.direction=='up' else min(.99,f.share_now/max(f.share_before,1e-6))) if label=='persistent' else 1.0
    decision(s,p,q.id,{'answer':answer},source);recompute(s,p)
    return True

@router.post('/plans/{pid}/questions/{qid}')
def answer_question(pid:str,qid:str,body:Answer):
    with session_scope() as s:
        p=plan_for(s,pid,['discover']);q=s.get(Question,qid)
        if not q or q.plan_id!=pid:raise HTTPException(404,'Question not found')
        record_interpretation(s,p,q,body.answer)
    return {'ok':True}

class DirectionEdit(BaseModel):
    bucket:Literal['more','less','clear','hold']
    factor:float=Field(ge=0,le=2,allow_inf_nan=False)
    districts:list[str]
def validate_direction(s,body):
    valid=set(s.scalars(select(Store.district)))
    if not body.districts or set(body.districts)-valid: raise HTTPException(422,'Select one or more known districts')
    if (body.bucket=='more' and body.factor<1) or (body.bucket=='less' and body.factor>1): raise HTTPException(422,'More requires factor >=1; less requires factor <=1')
@router.put('/plans/{pid}/directions/{did}')
def edit_direction(pid:str,did:str,body:DirectionEdit):
    with session_scope() as s:
        p=plan_for(s,pid,['direction']); d=s.get(DirectionItem,did)
        if not d or d.plan_id!=pid: raise HTTPException(404,'Direction not found')
        validate_direction(s,body)
        value=body.model_dump(); value['districts']=sorted(set(value['districts']))
        if all(getattr(d,k)==v for k,v in value.items()): return {'ok':True}
        for k,v in value.items(): setattr(d,k,v)
        decision(s,p,did,value); recompute(s,p)
    return {'ok':True}

class GoalEdit(BaseModel):
    goal:Literal['margin','fill_rate','sales']
    service_level:float|None=Field(default=None,ge=.5,le=.995,allow_inf_nan=False)
@router.put('/plans/{pid}/goal')
def edit_goal(pid:str,body:GoalEdit):
    with session_scope() as s:
        p=plan_for(s,pid,['discover','direction'])
        if p.goal==body.goal and p.service_level==body.service_level: return {'ok':True}
        p.goal=body.goal;p.service_level=body.service_level
        decision(s,p,'goal',body.model_dump()); recompute(s,p)
    return {'ok':True}

@router.post('/plans/{pid}/advance')
def advance(pid:str):
    with session_scope() as s:
        p=plan_for(s,pid,['discover','direction'])
        next_stage=STAGES[STAGES.index(p.stage)+1]
        decision(s,p,'stage_approved',{'from':p.stage,'to':next_stage})
        if next_stage=='execute':
            refresh_watches(s,p)
            from .. import workflow
            projection=projection_for(s,p)
            if workflow.confirm_review(s,p,projection):
                decision(s,p,'watch_review',{'confirmed':True,'selection':workflow.state(p)['review']['selection'],'combined_with_strategy':True})
            workflow.freeze_approval(s,p,projection)
            p.locked_at=datetime.now()
        p.stage=next_stage
        return {'stage':next_stage}

class Confirm(BaseModel): cases:int=Field(ge=0,strict=True)
@router.post('/plans/{pid}/orders/{sku}/confirm')
def confirm(pid:str,sku:str,body:Confirm):
    with session_scope() as s:
        p=plan_for(s,pid,['execute']); order=s.get(PurchaseSuggestion,(pid,sku)); product=s.get(Product,sku)
        if not order or not product: raise HTTPException(404,'Purchase suggestion not found')
        if order.status=='confirmed':
            if order.final_cases==body.cases: return {'ok':True}
            raise HTTPException(409,'Order already confirmed; repeated identical confirmation is safe.')
        if 0<body.cases<product.moq_cases: raise HTTPException(422,f'Minimum order is {product.moq_cases} cases, or zero to skip')
        orders=objects(s,PurchaseSuggestion,pid)
        capacity_result=None
        if body.cases>0:
            from ..planning import confirmation_capacity
            cases={o.sku:o.final_cases or 0 for o in orders if o.status=='confirmed'};cases[sku]=body.cases
            try: capacity_result=confirmation_capacity(p.week_start,cases)
            except Exception as exc: raise HTTPException(503,f'Capacity calculation failed: {type(exc).__name__}: {exc}') from exc
            if not capacity_result['feasible']: raise HTTPException(409,f"Order exceeds cold-store capacity on its dated arrival path: projected peak {capacity_result['projected_peak_pallets']:.2f} pallets, capacity {capacity_result['capacity_pallets']:.2f}, new excess {capacity_result['incremental_overcapacity_pallets']:.2f}. Reduce cases or skip.")
        order.final_cases=body.cases;order.status='confirmed'
        if body.cases:
            supplier=s.get(Supplier,product.supplier_id)
            s.add(PurchaseOrder(id='SC'+uuid4().hex[:28],sku=sku,supplier_id=product.supplier_id,order_date=order.order_date,expected_date=order.order_date+timedelta(days=supplier.lead_time_days),received_date=None,cases=body.cases,source='scoop'))
        decision(s,p,'confirm:'+sku,{'cases':body.cases,'synthetic':True,'supplier_transmission':False,'capacity':capacity_result})
    return {'ok':True}

@router.get('/plans/{pid}/orders.csv')
def export(pid:str):
    with session_scope() as s:
        plan_for(s,pid)
        rows=query(s,'SELECT ps.sku,p.name,ps.order_date,ps.suggested_cases,ps.capacity_cut_cases,COALESCE(ps.final_cases,GREATEST(ps.suggested_cases-ps.capacity_cut_cases,0)) AS effective_cases,ps.final_cases,ps.status,ps.reason FROM purchase_suggestions ps JOIN products p USING(sku) WHERE plan_id=:pid ORDER BY order_date,sku',pid=pid)
    output=io.StringIO(); writer=csv.DictWriter(output,fieldnames=['sku','name','order_date','suggested_cases','capacity_cut_cases','effective_cases','final_cases','status','reason']);writer.writeheader();writer.writerows(rows)
    return Response(output.getvalue(),media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="{pid}-orders.csv"'})

class WatchEdit(BaseModel):
    kind:Literal['fill_rate','capacity','days_cover','po_delay','tag_share']
    title:str=Field(min_length=1,max_length=160)
    assumption:str=Field(default='',max_length=2000)
    scope:dict=Field(default_factory=dict)

class WatchPatch(BaseModel):
    kind:Literal['fill_rate','capacity','days_cover','po_delay','tag_share']|None=None
    title:str|None=Field(default=None,min_length=1,max_length=160)
    assumption:str|None=Field(default=None,max_length=2000)
    scope:dict|None=None
def validate_watch(s,body):
    scope=body.scope
    if set(scope)-{'districts','tag_id','group','sku','skus','mode'}: raise HTTPException(422,'Unsupported watch scope')
    if 'districts' in scope and (not isinstance(scope['districts'],list) or any(not isinstance(d,str) for d in scope['districts']) or set(scope['districts'])-set(s.scalars(select(Store.district)))): raise HTTPException(422,'Unknown watch district')
    mode=scope.get('mode')
    if mode is not None and not isinstance(mode,str): raise HTTPException(422,'Watch mode must be a string')
    if mode is not None and ((body.kind=='days_cover' and mode not in {'below_lead','excess'}) or (body.kind=='capacity' and mode not in {'projected','observed'}) or body.kind not in {'days_cover','capacity'}): raise HTTPException(422,'Unsupported mode for this watch type')
    if body.kind=='capacity' and mode=='projected' and any(scope.get(key) for key in {'districts','tag_id','group','sku','skus'}): raise HTTPException(422,'Arrival occupancy projection covers the shared cold store; use an observed stock watch for an individual category')
    if scope.get('tag_id') and scope.get('group') and scope['tag_id']!=scope['group']: raise HTTPException(422,'Choose a single watch category')
    for key in {'tag_id','group','sku'}:
        if key in scope and (not isinstance(scope[key],str) or not scope[key]): raise HTTPException(422,'Category and SKU identifiers must be nonempty strings')
    tag=scope.get('tag_id',scope.get('group'))
    if tag:
        if not isinstance(tag,str): raise HTTPException(422,'Watch tag must be a string')
        group_skus(s,tag)
    skus=scope.get('skus',[])
    if not isinstance(skus,list) or any(not isinstance(k,str) or not s.get(Product,k) for k in skus): raise HTTPException(422,'Unknown watch SKU')
    if scope.get('sku'):
        if not s.get(Product,scope['sku']): raise HTTPException(422,'Unknown watch SKU')
        skus=[*skus,scope['sku']]
    if body.kind=='tag_share' and not tag and not skus: raise HTTPException(422,'Tag share requires a tag or SKU scope')
    if not body.title.strip(): raise HTTPException(422,'Watch title cannot be empty')

def add_watch(s,p,body,origin='ui'):
    from .. import workflow
    validate_watch(s,body)
    workflow.initialize_plan(s,p)
    scope=body.scope
    existing=s.scalar(select(WatchItem).where(WatchItem.plan_id==p.id,WatchItem.title==body.title))
    if existing:
        if existing.kind!=body.kind or existing.scope!=scope or existing.assumption!=body.assumption: raise HTTPException(409,'A different watch already has this title')
        if existing.status=='active': return existing.id
        existing.status='active'; wid=existing.id
    else:
        wid=p.id+'-W'+uuid4().hex[:16];s.add(WatchItem(id=wid,plan_id=p.id,kind=body.kind,title=body.title,assumption=body.assumption,scope=scope,origin='chat' if origin=='chat' else 'user',status='active'))
    workflow.mark_watch_edit(p,existing if existing else s.get(WatchItem,wid))
    workflow.invalidate_review(p)
    decision(s,p,'watch_added',{'id':wid,**body.model_dump()},origin);return wid
@router.post('/plans/{pid}/watch')
def new_watch(pid:str,body:WatchEdit):
    with session_scope() as s: return {'id':add_watch(s,plan_for(s,pid,STAGES),body)}
@router.delete('/plans/{pid}/watch/{wid}')
def archive_watch(pid:str,wid:str):
    from .. import workflow
    with session_scope() as s:
        p=plan_for(s,pid,STAGES);w=s.get(WatchItem,wid)
        if not w or w.plan_id!=pid: raise HTTPException(404,'Watch not found')
        if w.status!='archived':
            workflow.initialize_plan(s,p)
            w.status='archived';workflow.mark_watch_edit(p,w,archived=True);workflow.invalidate_review(p);decision(s,p,'watch_archived',{'id':wid})
    return {'ok':True}

@router.put('/plans/{pid}/watch/{wid}')
def edit_watch(pid:str,wid:str,body:WatchPatch):
    from .. import workflow
    with session_scope() as s:
        p=plan_for(s,pid,STAGES);w=s.get(WatchItem,wid)
        if not w or w.plan_id!=pid: raise HTTPException(404,'Watch not found')
        if w.status!='active': raise HTTPException(409,'Archived watch is read-only; restore it explicitly first')
        fields=body.model_dump(exclude_unset=True)
        if any(value is None for value in fields.values()): raise HTTPException(422,'Watch fields cannot be null')
        body=WatchEdit(**{**{key:getattr(w,key) for key in ['kind','title','assumption','scope']},**fields})
        validate_watch(s,body)
        other=s.scalar(select(WatchItem).where(WatchItem.plan_id==pid,WatchItem.title==body.title,WatchItem.id!=wid))
        if other: raise HTTPException(409,'A watch already uses this title')
        if all(getattr(w,key)==value for key,value in body.model_dump().items()): return {'ok':True}
        workflow.initialize_plan(s,p)
        for key,value in body.model_dump().items(): setattr(w,key,value)
        workflow.mark_watch_edit(p,w);workflow.invalidate_review(p)
        decision(s,p,'watch_edited',{'id':wid,**body.model_dump()})
    return {'ok':True}

class WatchReview(BaseModel): confirmed:Literal[True]
@router.post('/plans/{pid}/watch-review')
def review_watches(pid:str,body:WatchReview):
    from .. import workflow
    with session_scope() as s:
        p=plan_for(s,pid,STAGES)
        workflow.initialize_plan(s,p)
        if p.stage in {'discover','direction'}: refresh_watches(s,p)
        if workflow.confirm_review(s,p,projection_for(s,p)):
            decision(s,p,'watch_review',{'confirmed':True,'selection':workflow.state(p)['review']['selection']})
    return {'ok':True}

class ClockEdit(BaseModel): today:date
@router.put('/clock')
def clock(body:ClockEdit):
    if not MIN_DAY<=body.today<=MAX_DAY: raise HTTPException(422,'Demo clock supports 2026-06-01 through 2026-08-31')
    set_setting('today',body.today.isoformat());return {'today':body.today.isoformat()}

from ..ai.http import ChatRequest, answer as assistant_answer
class ChatEdit(ChatRequest):
    pass

class TemperatureScenario(BaseModel):
    temperature_c:float=Field(ge=15,le=45,allow_inf_nan=False)
    offset_days:Literal[0,7]=7

@router.post('/plans/{pid}/scenario')
def scenario(pid:str,body:TemperatureScenario):
    from ..ai.scenarios import temperature_scenario
    with session_scope() as s:
        return clean(temperature_scenario(s,plan_for(s,pid),body.temperature_c,body.offset_days))

@router.post('/plans/{pid}/chat')
def chat(pid:str,body:ChatEdit):
    with session_scope() as s:
        result=assistant_answer(s,plan_for(s,pid),body)
    return clean(result)


class PlayRequest(BaseModel):
    days: Literal[7, 14, 21] = 7

@router.post('/plans/{pid}/play')
def play(pid: str, body: PlayRequest):
    """Run the warehouse forward from the plan's Monday: this plan's orders vs the moving-average rule."""
    from ..play import simulate
    with session_scope() as s:
        p = plan_for(s, pid)
        week = p.week_start
    if week + timedelta(days=body.days - 1) > MAX_DAY: raise HTTPException(422, 'Not enough simulated days after this week to play that long.')
    try: return clean(simulate(pid, week, body.days))
    except Exception as exc: raise HTTPException(503, f'Play failed: {type(exc).__name__}: {exc}') from exc
