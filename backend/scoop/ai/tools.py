"""Finite, validated planning tools shared by the real conversational assistant.

The model chooses a tool; this module computes every number and applies only the
same stage-scoped business changes exposed in the planner UI. No SQL/code tool.
"""
from datetime import datetime, timedelta
from typing import Literal
from uuid import uuid4

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from ..models import DirectionItem, Finding, Hypothesis, Product, Question, Store, Tag, PurchaseSuggestion, WatchItem


class Parameters(BaseModel):
    model_config=ConfigDict(extra='forbid')


class FindingArgs(Parameters):
    finding_id:str


class OrderArgs(Parameters):
    sku:str


class ScenarioArgs(Parameters):
    temperature_c:float=Field(ge=15,le=45,allow_inf_nan=False)
    offset_days:Literal[0,7]=7


class ClassifyArgs(FindingArgs):
    interpretation:Literal['persistent','one_off','data_issue','weather','unsure','mirror']


class GoalArgs(Parameters):
    goal:Literal['margin','fill_rate','sales']
    service_level:float|None=Field(default=None,ge=.5,le=.995,allow_inf_nan=False)


class DirectionArgs(Parameters):
    tag_id:str|None=None
    sku:str|None=None
    bucket:Literal['more','less','hold','clear']
    factor:float=Field(ge=0,le=2,allow_inf_nan=False)
    districts:list[str]=Field(min_length=1)


class ScopeArgs(Parameters):
    tag_id:str|None=None
    sku:str|None=None
    districts:list[str]=Field(default_factory=list)


class MetricArgs(ScopeArgs):
    kind:Literal['fill_rate','days_cover','capacity','po_delay','tag_share']


class WatchArgs(MetricArgs):
    title:str=Field(min_length=1,max_length=160)
    assumption:str=Field(min_length=1,max_length=2000)


TOOL_MODELS={
    'inspect_finding':(FindingArgs,'Read evidence and alternative explanations for one finding in the active plan.'),
    'inspect_order':(OrderArgs,'Read a SKU recommendation, case size, demand range, inventory and purchasing rationale.'),
    'inspect_metric':(MetricArgs,'Calculate a historical metric with optional category/SKU and district scope. Stockout concerns use fill_rate because there is no store-level stock ledger.'),
    'temperature_scenario':(ScenarioArgs,'Recompute purchasing with a temperature change in this or next week. Read-only: does not change directions or orders.'),
    'classify_finding':(ClassifyArgs,'Record the user’s explicit interpretation of a finding during Discover and recompute direction/purchases.'),
    'set_goal':(GoalArgs,'Apply an explicitly requested buying objective and optional service target before strategy approval.'),
    'set_direction':(DirectionArgs,'Apply an explicitly requested category OR SKU buying direction during Direction. Factor 1.10 means ten percent more; 0.90 means ten percent less. Use exact catalog IDs.'),
    'add_watch':(WatchArgs,'Add an explicitly requested watch for an assumption, category/SKU or district. Does not place orders.'),
}
MUTATING={'classify_finding','set_goal','set_direction','add_watch'}


def declarations():
    return [{'name':name,'description':description,'parametersJsonSchema':model.model_json_schema()}
            for name,(model,description) in TOOL_MODELS.items()]


def context(session,plan,focus=None):
    from ..api.service import clean,objects,row
    from .narrator import saved_explanation
    findings=objects(session,Finding,plan.id)
    orders=objects(session,PurchaseSuggestion,plan.id)
    return clean({
        'plan':{'id':plan.id,'week_start':plan.week_start,'stage':plan.stage,'goal':plan.goal,'service_level':plan.service_level},
        'focus':focus or {},'data_kind':'synthetic demonstration, not sponsor/customer data',
        'cutoff':plan.week_start-timedelta(days=1),
        'findings':[{'id':f.id,'category':f.evidence.get('display',f.tag_id),'tag_id':f.tag_id,'districts':f.evidence.get('districts',[]),'direction':f.direction,'interpretation':f.classification,'summary':saved_explanation(f)} for f in findings],
        'directions':[row(d) for d in objects(session,DirectionItem,plan.id)],
        'watches':[{'id':w.id,'title':w.title,'scope':w.scope,'assumption':w.assumption} for w in objects(session,WatchItem,plan.id) if w.status=='active'],
        'purchase_summary':{'positive_skus':sum((o.final_cases if o.final_cases is not None else max(0,o.suggested_cases-o.capacity_cut_cases))>0 for o in orders),'cases':sum(o.final_cases if o.final_cases is not None else max(0,o.suggested_cases-o.capacity_cut_cases) for o in orders)},
        'catalog':[{'sku':p.sku,'name':p.name} for p in session.scalars(select(Product).order_by(Product.sku))],
        'tags':[{'id':t.id,'name':t.name} for t in session.scalars(select(Tag)) if ':' in t.id],
        'districts':sorted(set(session.scalars(select(Store.district)))),
        'rules':['Existing products only; no shelf allocation or supplier transmission.','Numbers come from tools. Do not invent operational impact.','Historical stock does not change when demo purchases are confirmed.'],
    })


def _scope(session,args):
    from ..api.service import group_skus
    scope={}
    if args.tag_id:
        group_skus(session,args.tag_id);scope['tag_id']=args.tag_id
    if args.sku:
        if not session.get(Product,args.sku): raise ValueError('Choose a product from this catalog.')
        scope['sku']=args.sku
    if args.tag_id and args.sku: raise ValueError('Choose one product or one category, rather than both.')
    if args.districts:
        if set(args.districts)-set(session.scalars(select(Store.district))): raise ValueError('Choose districts in this network.')
        scope['districts']=sorted(set(args.districts))
    return scope


def execute(name,arguments,session,plan,stage):
    from ..api.service import clean,objects,row,decision,recompute,validate_direction,DirectionEdit,WatchEdit,add_watch,watch_view,today
    if name not in TOOL_MODELS: raise ValueError('This planning tool is not supported.')
    args=TOOL_MODELS[name][0].model_validate(arguments)
    if name in MUTATING:
        session.refresh(plan,with_for_update=True)
        allowed={'classify_finding':['discover'],'set_goal':['discover','direction'],'set_direction':['direction'],'add_watch':['discover','direction','execute']}[name]
        if plan.stage!=stage or plan.stage not in allowed:
            raise HTTPException(409,'This step is already approved. View the current step to make a new decision.')
        if plan.week_start>today(): raise HTTPException(409,'This plan is later than the demo date.')
    if name=='inspect_finding':
        finding=session.get(Finding,args.finding_id)
        if not finding or finding.plan_id!=plan.id: raise ValueError('This finding is not in the current plan.')
        hypotheses=[row(h) for h in session.scalars(select(Hypothesis).where(Hypothesis.finding_id==finding.id))]
        from .narrator import saved_explanation
        return clean({'finding':{**row(finding),'explanation':saved_explanation(finding)},'hypotheses':hypotheses,'facts_through':plan.week_start-timedelta(days=1)}),None
    if name=='inspect_order':
        order=session.get(PurchaseSuggestion,(plan.id,args.sku));product=session.get(Product,args.sku)
        if not order or not product: raise ValueError('This product has no suggestion in the current plan.')
        return clean({'product':{'sku':product.sku,'name':product.name,'units_per_case':product.units_per_case},'order':row(order),'effective_cases':order.final_cases if order.final_cases is not None else max(0,order.suggested_cases-order.capacity_cut_cases)}),None
    if name=='temperature_scenario':
        from .scenarios import temperature_scenario
        result=temperature_scenario(session,plan,args.temperature_c,args.offset_days)
        return result,{'type':'scenario','result':result}
    if name=='inspect_metric':
        scope=_scope(session,args)
        if args.kind=='tag_share' and not (args.tag_id or args.sku): raise ValueError('Choose a category or product for its demand share.')
        if args.kind in {'capacity','days_cover'} and args.districts: raise ValueError('Warehouse stock is shared across districts. Use district fill rate to inspect shortages.')
        watch=WatchItem(id='preview',plan_id=plan.id,kind=args.kind,title='Requested measure',assumption='',scope=scope,origin='chat',status='active')
        return watch_view(session,watch,min(today(),plan.week_start+timedelta(days=7))),None
    if name=='classify_finding':
        finding=session.get(Finding,args.finding_id)
        if not finding or finding.plan_id!=plan.id: raise ValueError('Choose a finding from the current plan.')
        question=session.scalar(select(Question).where(Question.plan_id==plan.id,Question.finding_id==finding.id))
        if not question: raise ValueError('This finding is a watch-only signal; it has no interpretation question.')
        from ..api.service import record_interpretation
        record_interpretation(session,plan,question,args.interpretation,'chat')
        result={'finding_id':finding.id,'category':finding.evidence.get('display',finding.tag_id),'interpretation':args.interpretation,'applied':True}
        return result,{'type':'classification',**result}
    if name=='set_goal':
        if plan.goal!=args.goal or plan.service_level!=args.service_level:
            plan.goal=args.goal;plan.service_level=args.service_level
            decision(session,plan,'goal',args.model_dump(),'chat');recompute(session,plan)
        result={**args.model_dump(),'applied':True}
        return result,{'type':'goal',**result}
    if name=='set_direction':
        _scope(session,args)
        if not (args.tag_id or args.sku):raise ValueError('Choose a category or product.')
        validate_direction(session,DirectionEdit(bucket=args.bucket,factor=args.factor,districts=args.districts))
        column=DirectionItem.tag_id if args.tag_id else DirectionItem.sku
        target=args.tag_id or args.sku
        direction=session.scalar(select(DirectionItem).where(DirectionItem.plan_id==plan.id,column==target))
        values={'bucket':args.bucket,'factor':args.factor,'districts':sorted(set(args.districts))}
        changed=direction is None or any(getattr(direction,k)!=v for k,v in values.items())
        if direction is None:
            direction=DirectionItem(id=plan.id+'-D'+uuid4().hex[:16],plan_id=plan.id,tag_id=args.tag_id,sku=args.sku,note='Agreed in plan discussion',**values)
            session.add(direction);session.flush()
        else:
            for k,v in values.items():setattr(direction,k,v)
        if changed:decision(session,plan,direction.id,values,'chat');recompute(session,plan)
        result={'id':direction.id,**values,'applied':True}
        return result,{'type':'direction',**result}
    if name=='add_watch':
        scope=_scope(session,args)
        if args.kind in {'capacity','days_cover'} and args.districts:raise ValueError('Use fill rate for district-specific shortages; warehouse stock is shared.')
        wid=add_watch(session,plan,WatchEdit(kind=args.kind,title=args.title,assumption=args.assumption,scope=scope),origin='chat')
        result={'id':wid,'title':args.title,'scope':scope,'applied':True}
        return result,{'type':'watch',**result}
    raise ValueError('Unsupported planning tool.')
