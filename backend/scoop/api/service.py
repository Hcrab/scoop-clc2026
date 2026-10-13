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

def objects(s, cls, pid): return s.scalars(select(cls).where(cls.plan_id == pid)).all()

def recompute(s, p):
    from ..planning import suggest_orders, reason_text
    directions = [row(d) for d in objects(s, DirectionItem, p.id)]
    try: orders = suggest_orders(p.week_start, directions, service_level=p.service_level, goal=p.goal)
    except Exception as exc: raise HTTPException(503, f'Forecast recomputation failed: {type(exc).__name__}: {exc}') from exc
    names = dict(s.execute(select(Product.sku, Product.name)).all())
    s.execute(delete(PurchaseSuggestion).where(PurchaseSuggestion.plan_id == p.id))
    for r in orders.itertuples():
        fields = {k: clean(getattr(r, k)) for k in ['sku', 'order_date', 'demand_p10', 'demand_p50', 'demand_p90', 'adjustment', 'critical_ratio', 'target_units', 'on_hand_units', 'on_order_units', 'inventory_position', 'suggested_cases', 'capacity_cut_cases']}
        s.add(PurchaseSuggestion(plan_id=p.id, protection_days=int(r.pdays), final_cases=None, status='suggested', reason=reason_text(r, names, directions), **fields))
    p.summary={**(p.summary or {}),'orders_due':int((orders.suggested_cases-orders.capacity_cut_cases>0).sum()),'goal':p.goal}

def catalog(s):
    suppliers = {x.id: x for x in s.scalars(select(Supplier))}
    nutrition = {x.sku: row(x) for x in s.scalars(select(ProductNutrition))}
    tags = query(s, 'SELECT pt.sku, t.id, t.name, t.dimension_id AS dimension, pt.value_num AS value FROM product_tags pt JOIN tags t ON t.id=pt.tag_id ORDER BY t.id')
    return [dict(row(p), lead_time_days=suppliers[p.supplier_id].lead_time_days, order_weekday=suppliers[p.supplier_id].order_weekday, tags=[{k:v for k,v in t.items() if k != 'sku'} for t in tags if t['sku']==p.sku], nutrition=nutrition.get(p.sku, {})) for p in s.scalars(select(Product).order_by(Product.sku))]

def metrics(s, cutoff, store=None):
    data = query(s, 'SELECT COALESCE(SUM(ordered_units),0) AS ordered_units, COALESCE(SUM(shipped_units),0) AS shipped_units FROM store_orders WHERE date>=:start AND date<:end' + (' AND store_id=:store' if store else ''), start=cutoff-timedelta(days=7), end=cutoff, store=store)[0]
    data['fill_rate'] = data['shipped_units']/data['ordered_units'] if data['ordered_units'] else 0
    return data

def plan_metrics(s, cutoff):
    result=metrics(s,cutoff)
    result.update(query(s,'SELECT COALESCE(SUM(n.on_hand_units),0) AS on_hand_units, COALESCE(SUM(n.on_hand_units::float/(p.units_per_case*p.cases_per_pallet)),0) AS pallets_used FROM node_inventory n JOIN products p USING(sku) WHERE n.date=:day',day=cutoff-timedelta(days=1))[0])
    return result

def refresh_watches(s,p):
    from ..planning import watch_items
    findings=[{'kind':f.kind,'group':f.tag_id,'display':f.evidence.get('display',f.tag_id),'districts':f.evidence.get('districts',f.district.split(', '))} for f in objects(s,Finding,p.id)]
    generated=watch_items(findings,[row(d) for d in objects(s,DirectionItem,p.id)])
    wanted={w['title'] for w in generated}
    existing={w.title:w for w in objects(s,WatchItem,p.id)}
    for w in existing.values():
        if w.origin in {'baseline','decision'} and len(w.id.rsplit('-W',1)[-1])==12 and w.title not in wanted: w.status='archived'
    for values in generated:
        w=existing.get(values['title'])
        if w is None:
            w=WatchItem(id=p.id+'-W'+hashlib.sha256(values['title'].encode()).hexdigest()[:12],plan_id=p.id,status='active',**values);s.add(w)
        elif w.origin in {'baseline','decision'}:
            for key,value in values.items(): setattr(w,key,value)

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
        return clean(dict(today=day, provider='scripted', synthetic=True, plans=[row(p) for p in s.scalars(select(Plan).where(Plan.week_start<=day).order_by(Plan.week_start.desc()))], stores=[row(x) for x in s.scalars(select(Store).order_by(Store.id))], products=catalog(s), node=row(node) if node else None, metrics=m, evaluation=evaluation_data() if (settings.reports_dir/'evaluation.json').exists() else None, metadata={'inventory_provenance':PROVENANCE,'facts_through':day-timedelta(days=1),'clock_range':[MIN_DAY,MAX_DAY],'week_switch':'Selecting a plan reads history; only explicit clock changes change the as-of date.'}))

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

def watch_view(s, w, cutoff, projection=None):
    if w.scope.get('mode')=='projected' and projection:
        return clean({**row(w),'value':projection['projected_peak_pallets'],'unit':'pallets','state':'normal' if projection['projected_peak_pallets']<=projection['capacity_pallets'] else 'warning','series':projection['series'],'provenance':'Frozen plan-date projection including proposed and confirmed case quantities.'})
    result=row(w); facts=scoped_facts(s,w.scope,cutoff)
    sku_scope=w.scope.get('skus', [w.scope['sku']] if w.scope.get('sku') else [])
    tag=w.scope.get('tag_id',w.scope.get('group'))
    if tag: sku_scope=group_skus(s,tag)
    inventory=query(s,'SELECT n.date,n.sku,n.on_hand_units,p.units_per_case,p.cases_per_pallet,su.lead_time_days FROM node_inventory n JOIN products p USING(sku) JOIN suppliers su ON su.id=p.supplier_id WHERE n.date>=:start AND n.date<:cutoff AND (:all_skus OR n.sku=ANY(:skus)) ORDER BY n.date',start=cutoff-timedelta(days=28),cutoff=cutoff,all_skus=not sku_scope,skus=sku_scope)
    series=[]
    for day in sorted({r['date'] for r in facts}):
        f=[r for r in facts if r['date']==day]; inv=[r for r in inventory if r['date']==day]
        ordered=sum(r['ordered_units'] for r in f); shipped=sum(r['shipped_units'] for r in f)
        if w.kind=='fill_rate': value=shipped/ordered if ordered else 0; unit='ratio'
        elif w.kind=='capacity': value=sum(r['on_hand_units']/(r['units_per_case']*r['cases_per_pallet']) for r in inv); unit='pallets'
        elif w.kind=='days_cover':
            recent=[r for r in facts if day-timedelta(days=7)<r['date']<=day]
            mode=w.scope.get('mode')
            if mode in {'below_lead','excess'}:
                if day<cutoff-timedelta(days=21): continue
                demand={r['sku']:0.0 for r in inv}
                for r in recent: demand[r['sku']]=demand.get(r['sku'],0)+r['ordered_units']/7
                def flagged(r):
                    mean=demand.get(r['sku'],0)
                    if not mean: return mode=='excess' and r['on_hand_units']>0
                    cover=r['on_hand_units']/mean
                    return cover<r['lead_time_days'] if mode=='below_lead' else cover>2*(r['lead_time_days']+7)
                value=sum(flagged(r) for r in inv);unit='SKUs'
            else:
                demand=sum(r['ordered_units'] for r in recent)/7
                value=sum(r['on_hand_units'] for r in inv)/demand if demand else 0; unit='days'
        elif w.kind=='po_delay':
            value=query(s,"SELECT count(*) AS n FROM purchase_orders WHERE source='history' AND order_date<=:day AND expected_date<:day AND (received_date IS NULL OR received_date>:day) AND (:all_skus OR sku=ANY(:skus))",day=day,all_skus=not sku_scope,skus=sku_scope)[0]['n']; unit='orders'
        else:
            total=query(s,'SELECT COALESCE(SUM(o.ordered_units),0) AS n FROM store_orders o JOIN stores st ON st.id=o.store_id WHERE o.date=:day AND (:all_districts OR st.district=ANY(:districts))',day=day,all_districts=not w.scope.get('districts'),districts=w.scope.get('districts',[]))[0]['n']
            value=ordered/total if total else 0; unit='ratio'
        series.append({'date':day,'value':value})
    value=series[-1]['value'] if series else 0
    node=s.scalar(select(Node))
    warning=(w.kind=='fill_rate' and value<.97) or (w.kind=='capacity' and node and value>node.capacity_pallets) or (w.kind=='po_delay' and value>0) or (w.kind=='days_cover' and (value>0 if w.scope.get('mode') in {'below_lead','excess'} else value<7))
    state='warning' if warning else 'normal'
    if w.kind=='tag_share':
        # A chart for judgement, not another statistically calibrated alert gate.
        state='review'
        if tag:
            districts=w.scope.get('districts') or sorted(set(s.scalars(select(Store.district))))
            expected=cached_series(tag,districts,cutoff-timedelta(days=28),cutoff)
            if expected: series=[{'date':r['date'],'value':r['actual_share'],'expected':r['expected_share']} for r in expected];value=series[-1]['value']
    result.update(value=value,unit=unit if series else 'n/a',state=state,series=series,provenance=PROVENANCE)
    return clean(result)

def cached_series(tag, districts, start, cutoff):
    """Recovered algorithms persist charts in their trusted local model cache."""
    from ..monitoring import monitoring
    series=monitoring().series
    import pandas as pd
    selected=series[(series['group']==tag)&series.district.isin(districts)&(series.date>=pd.Timestamp(start))&(series.date<pd.Timestamp(cutoff))]
    if selected.empty: return []
    return clean(selected.groupby('date').agg(actual_share=('actual_share','mean'),expected_share=('expected_share','mean'),s_up=('s_up','max'),s_down=('s_down','max')).reset_index().to_dict('records'))

@router.get('/plans/{pid}')
def get_plan(pid:str):
    with session_scope() as s:
        p=plan_for(s,pid); cutoff=min(today(),p.week_start+timedelta(days=7))
        findings=[]
        for f in objects(s,Finding,pid):
            item=row(f)
            item['hypotheses']=[row(h) for h in s.scalars(select(Hypothesis).where(Hypothesis.finding_id==f.id))]
            item['series']=query(s,'SELECT date, AVG(actual_share) AS actual_share, AVG(expected_share) AS expected_share, MAX(s_up) AS s_up, MAX(s_down) AS s_down FROM cusum_series WHERE tag_id=:tag AND date<:cutoff AND date>=:start AND district=ANY(:districts) GROUP BY date ORDER BY date',tag=f.tag_id,cutoff=min(cutoff,p.week_start),start=p.week_start-timedelta(days=56),districts=f.evidence.get('districts',f.district.split(', ')))
            if not item['series']:
                item['series']=cached_series(f.tag_id,f.evidence.get('districts',f.district.split(', ')),p.week_start-timedelta(days=56),min(cutoff,p.week_start))
            findings.append(item)
        questions=[]
        for q in objects(s,Question,pid):
            item=row(q); options=q.options if isinstance(q.options,dict) else {'options':q.options}
            item['options']={'options':[{'id':o.get('id',o.get('value')),'label':o.get('label',o.get('value'))} for o in options.get('options',[])],'recommended':options.get('recommended','unsure')}; questions.append(item)
        orders=query(s,'SELECT ps.*, p.name,p.brand,p.units_per_case,p.moq_cases,s.name AS supplier_name FROM purchase_suggestions ps JOIN products p USING(sku) JOIN suppliers s ON s.id=p.supplier_id WHERE ps.plan_id=:pid ORDER BY ps.order_date,p.name',pid=pid)
        for order in orders: order['effective_cases']=order['final_cases'] if order['final_cases'] is not None else max(0,order['suggested_cases']-order['capacity_cut_cases'])
        watches=[w for w in objects(s,WatchItem,pid) if w.status=='active']
        projection=None
        if any(w.scope.get('mode')=='projected' for w in watches):
            from ..planning import confirmation_capacity
            projection=confirmation_capacity(p.week_start,{o['sku']:o['effective_cases'] for o in orders})
        return clean({'plan':row(p),'metrics':plan_metrics(s,p.week_start),'findings':findings,'questions':questions,'directions':[row(d) for d in objects(s,DirectionItem,pid)],'orders':orders,'watch':[watch_view(s,w,cutoff,projection) for w in watches],'decisions':[row(x) for x in objects(s,Decision,pid)],'messages':[row(x) for x in s.scalars(select(ChatMessage).where(ChatMessage.plan_id==pid).order_by(ChatMessage.id))],'metadata':{'inventory_provenance':PROVENANCE,'facts_through':cutoff-timedelta(days=1)}})

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
        try: return {'id':build_plan(week)}
        except Exception as exc: raise HTTPException(503,f'Plan generation failed: {type(exc).__name__}: {exc}') from exc

class Answer(BaseModel): answer:str
@router.post('/plans/{pid}/questions/{qid}')
def answer_question(pid:str,qid:str,body:Answer):
    with session_scope() as s:
        p=plan_for(s,pid,['discover']); q=s.get(Question,qid)
        if not q or q.plan_id!=pid: raise HTTPException(404,'Question not found')
        if q.stage!=p.stage: raise HTTPException(409,'Question stage is read-only')
        allowed={'persistent','one_off','data_issue','weather','unsure','watch','mirror'}
        if body.answer not in allowed: raise HTTPException(422,'Unsupported finding interpretation')
        if q.answer==body.answer: return {'ok':True}
        q.answer=body.answer; q.answered_at=datetime.now(); label='unsure' if body.answer=='watch' else body.answer
        f=s.get(Finding,q.finding_id) if q.finding_id else None
        if f:
            f.classification=label
            original=f.evidence.get('original_explanation',f.explanation)
            f.evidence={**f.evidence,'original_explanation':original,'human_interpretation':label}
            f.explanation=f'Planner interpretation: {label.replace("_"," ")}. Observed evidence: {original}'
            for h in s.scalars(select(Hypothesis).where(Hypothesis.finding_id==f.id)): h.selected=h.label==label
            for d in objects(s,DirectionItem,pid):
                if d.finding_id==f.id:
                    d.bucket=('more' if f.direction=='up' else 'less') if label=='persistent' else 'hold'
                    d.factor=(max(1.01,f.share_now/max(f.share_before,1e-6)) if f.direction=='up' else min(.99,f.share_now/max(f.share_before,1e-6))) if label=='persistent' else 1.0
        decision(s,p,qid,{'answer':body.answer},'question'); recompute(s,p)
    return {'ok':True}

class DirectionEdit(BaseModel):
    bucket:Literal['more','less','clear','hold']
    factor:float=Field(ge=0,allow_inf_nan=False)
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
        if p.stage=='discover' and any(q.answer is None for q in objects(s,Question,pid)): raise HTTPException(409,'Answer the discovery questions before approving this stage')
        next_stage=STAGES[STAGES.index(p.stage)+1]
        decision(s,p,'stage_approved',{'from':p.stage,'to':next_stage})
        p.stage=next_stage
        if next_stage=='execute':
            p.locked_at=datetime.now()
            refresh_watches(s,p)
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
def add_watch(s,p,body,origin='ui'):
    scope=body.scope
    if set(scope)-{'districts','tag_id','group','sku','skus'}: raise HTTPException(422,'Unsupported watch scope')
    if scope.get('districts') and (not isinstance(scope['districts'],list) or any(not isinstance(d,str) for d in scope['districts']) or set(scope['districts'])-set(s.scalars(select(Store.district)))): raise HTTPException(422,'Unknown watch district')
    tag=scope.get('tag_id',scope.get('group'))
    if tag:
        if not isinstance(tag,str): raise HTTPException(422,'Watch tag must be a string')
        group_skus(s,tag)
    skus=scope.get('skus',[scope['sku']] if scope.get('sku') else [])
    if not isinstance(skus,list) or any(not isinstance(k,str) or not s.get(Product,k) for k in skus): raise HTTPException(422,'Unknown watch SKU')
    if body.kind=='tag_share' and not tag and not skus: raise HTTPException(422,'Tag share requires a tag or SKU scope')
    existing=s.scalar(select(WatchItem).where(WatchItem.plan_id==p.id,WatchItem.title==body.title))
    if existing:
        if existing.kind!=body.kind or existing.scope!=scope or existing.assumption!=body.assumption: raise HTTPException(409,'A different watch already has this title')
        if existing.status=='active': return existing.id
        existing.status='active'; wid=existing.id
    else:
        wid=p.id+'-W'+uuid4().hex[:16];s.add(WatchItem(id=wid,plan_id=p.id,kind=body.kind,title=body.title,assumption=body.assumption,scope=scope,origin='chat' if origin=='chat' else 'user',status='active'))
    decision(s,p,'watch_added',{'id':wid,**body.model_dump()},origin);return wid
@router.post('/plans/{pid}/watch')
def new_watch(pid:str,body:WatchEdit):
    with session_scope() as s: return {'id':add_watch(s,plan_for(s,pid,STAGES),body)}
@router.delete('/plans/{pid}/watch/{wid}')
def archive_watch(pid:str,wid:str):
    with session_scope() as s:
        p=plan_for(s,pid,STAGES);w=s.get(WatchItem,wid)
        if not w or w.plan_id!=pid: raise HTTPException(404,'Watch not found')
        if w.status!='archived': w.status='archived';decision(s,p,'watch_archived',{'id':wid})
    return {'ok':True}

class ClockEdit(BaseModel): today:date
@router.put('/clock')
def clock(body:ClockEdit):
    if not MIN_DAY<=body.today<=MAX_DAY: raise HTTPException(422,'Demo clock supports 2026-06-01 through 2026-08-31')
    set_setting('today',body.today.isoformat());return {'today':body.today.isoformat()}

class ChatEdit(BaseModel):
    message:str=Field(min_length=1,max_length=4000)
    stage:Literal['discover','direction','execute']

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
    from ..ai.chat import respond
    with session_scope() as s:
        p=plan_for(s,pid)
        reply,actions=respond(s,p,body.message,body.stage)
        for role,content in [('user',body.message),('assistant',reply)]: s.add(ChatMessage(plan_id=pid,stage=body.stage,role=role,content=content,meta={'provider':'scripted','actions':actions if role=='assistant' else []},created_at=datetime.now()))
    return {'reply':reply,'provider':'scripted','actions':actions}
