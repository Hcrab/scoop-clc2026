"""Finite, validated planning tools shared by the real conversational assistant.

The model chooses a tool; this module computes every number and applies only
validated business changes exposed in the planner UI. No SQL/code tool.
"""
from datetime import timedelta
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from ..models import Finding, Hypothesis, Product, Store, Tag, PurchaseSuggestion, WatchItem


class Parameters(BaseModel):
    model_config=ConfigDict(extra='forbid')


class FindingArgs(Parameters):
    finding_id:str


class DiscussionArgs(Parameters):
    operation:Literal['add','reopen','resolve']
    topic_id:str|None=Field(default=None,max_length=120)
    title:str|None=Field(default=None,min_length=1,max_length=160)
    note:str|None=Field(default=None,max_length=2000)
    finding_id:str|None=Field(default=None,max_length=120)



class OrderArgs(Parameters):
    sku:str


class ScenarioArgs(Parameters):
    temperature_c:float=Field(ge=15,le=45,allow_inf_nan=False)
    offset_days:Literal[0,7]=7


class GoalArgs(Parameters):
    goal:Literal['margin','fill_rate','sales']
    service_level:float|None=Field(default=None,ge=.5,le=.995,allow_inf_nan=False)


class OverrideArgs(Parameters):
    cohort:str|None=None
    tag_path:list[dict]=Field(default_factory=list)
    districts:list[str]=Field(default_factory=list)
    type:Literal['one_off','ends_on','cap','expect','cases']
    value:object=None
    note:str=Field(default='',max_length=2000)


class UndoArgs(Parameters):
    edit_id:int


class BulkFilterArgs(Parameters):
    tag:str|None=None
    group:str|None=None
    cohort:str|None=None
    family:str|None=None
    brand:str|None=None
    district:str|None=None
    skus:list[str]=Field(default_factory=list)


class BulkChangeArgs(Parameters):
    type:Literal['percent','set_cases','fit_capacity']
    value:float|int


class BulkArgs(Parameters):
    filter:BulkFilterArgs=Field(default_factory=BulkFilterArgs)
    change:BulkChangeArgs


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
    'update_discussion':(DiscussionArgs,'Manage the advisory discussion agenda: add a genuinely new follow-up, resolve a topic after a useful answer or clear acknowledgement, or reopen uncertainty. Available for informational conversations without an explicit business edit request. Does not classify findings, change buying goals/directions, approve stages, or confirm orders. Use current-plan topic and finding IDs.'),
    'inspect_finding':(FindingArgs,'Read evidence and alternative explanations for one finding in the active plan.'),
    'inspect_order':(OrderArgs,'Read a SKU recommendation, case size, demand range, inventory and purchasing rationale.'),
    'inspect_metric':(MetricArgs,'Calculate a historical metric with optional category/SKU and district scope. Stockout concerns use fill_rate because there is no store-level stock ledger.'),
    'temperature_scenario':(ScenarioArgs,'Recompute purchasing with a temperature change in this or next week. Read-only: does not change the plan or orders.'),
    'set_goal':(GoalArgs,'Apply an explicitly requested buying objective or service target and return an undoable edit.'),
    'set_override':(OverrideArgs,'Apply an explicitly requested cohort context change at any plan stage. Use an exact cohort card ID, or its exact tag_path and districts. For a stated end date use ends_on with ISO date even when the user also says one-off. Returns an undoable edit.'),
    'bulk_edit_orders':(BulkArgs,'Change final order cases for an exact catalog filter. Percent is signed points, e.g. 10 means 10% more and -10 means 10% less; set_cases is a whole nonnegative case count. fit_capacity uses a fraction 0-1 of warehouse capacity on the whole plan. Never invent a missing amount.'),
    'undo_edit':(UndoArgs,'Undo a specific prior context edit only when the user explicitly requests it. Use the edit_id from the saved edit.'),
    'add_watch':(WatchArgs,'Add an explicitly requested watch for an assumption, category/SKU or district. Does not place orders.'),
}
MUTATING={'set_override','bulk_edit_orders','undo_edit','set_goal','add_watch'}


def declarations():
    from .exploration_tools import declarations as exploration_declarations
    return [{'name':name,'description':description,'parametersJsonSchema':model.model_json_schema()}
            for name,(model,description) in TOOL_MODELS.items()]+exploration_declarations()


def context(session,plan,focus=None):
    import json
    from .exploration_tools import _groups
    from ..cohort_context import load_overrides
    from ..discussion import view
    from ..api.service import clean,objects
    from .narrator import saved_explanation
    findings=objects(session,Finding,plan.id)
    orders=objects(session,PurchaseSuggestion,plan.id)
    return clean({
        'plan':{'id':plan.id,'week_start':plan.week_start,'stage':plan.stage,'goal':plan.goal,'service_level':plan.service_level},
        'discussion':view(session,plan),'focus':focus or {},'data_kind':'synthetic demonstration, not sponsor/customer data',
        'weekly_review':{k:v for k,v in (plan.summary or {}).get('weekly_review',{}).items() if k in {'status','report','claims','model'}},
        'review_evidence':[{'id':q['id'],'name':q['name'],'args':q['args'],'result_excerpt':json.dumps(q['result'],ensure_ascii=False)[:2500]} for q in (plan.summary or {}).get('weekly_review',{}).get('queries',[])],
        'cutoff':plan.week_start-timedelta(days=1),
        'findings':[{'id':f.id,'category':f.evidence.get('display',f.tag_id),'tag_id':f.tag_id,'districts':f.evidence.get('districts',[]),'summary':saved_explanation(f)} for f in findings],
        'cohorts':[{'id':c['id'],'name':c.get('name'),'tag_path':c['tag_path'],'districts':c['districts'],'skus':c.get('skus',[])} for c in (plan.summary or {}).get('cohort_cards',[])],
        'cohort_leaves':[{'id':c['id'],'tag_path':c['tag_path'],'districts':c['districts'],'skus':c.get('skus',[])} for c in (plan.summary or {}).get('cohort_model',{}).get('leaves',[])],
        'active_overrides':load_overrides(session,plan.week_start),
        'watches':[{'id':w.id,'title':w.title,'scope':w.scope,'assumption':w.assumption} for w in objects(session,WatchItem,plan.id) if w.status=='active'],
        'purchase_summary':{'positive_skus':sum((o.final_cases if o.final_cases is not None else max(0,o.suggested_cases-o.capacity_cut_cases))>0 for o in orders),'cases':sum(o.final_cases if o.final_cases is not None else max(0,o.suggested_cases-o.capacity_cut_cases) for o in orders)},
        'catalog':[{'sku':p.sku,'name':p.name} for p in session.scalars(select(Product).order_by(Product.sku))],
        'order_groups':[{'id':g.id,'name':g.name,'skus':list(g.skus)} for g in _groups(session).values()],
        'brands':sorted(set(session.scalars(select(Product.brand)))),
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
    from ..api.service import clean,objects,row,decision,recompute,WatchEdit,add_watch,watch_view,today
    if name in {'catalog_groups','query_group','query_operations','preview_group_orders'}:
        from .exploration_tools import execute as explore
        return clean(explore(name,arguments,session,plan)),None
    if name not in TOOL_MODELS: raise ValueError('This planning tool is not supported.')
    args=TOOL_MODELS[name][0].model_validate(arguments)
    if name=='update_discussion':
        from ..discussion import update
        result=update(session,plan,args)
        return {'discussion':result,'applied':True},{'type':'discussion','discussion':result}
    if name in MUTATING:
        session.refresh(plan,with_for_update=True)
        allowed={'set_override':['discover','direction','execute'],'bulk_edit_orders':['discover','direction','execute'],'undo_edit':['discover','direction','execute'],'set_goal':['discover','direction','execute'],'add_watch':['discover','direction','execute']}[name]
        if plan.stage not in allowed:
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
    if name=='set_override':
        from ..api.cohorts import OverrideRequest,change_context
        label=next((c.get('name') for c in (plan.summary or {}).get('cohort_cards',[]) if c['id']==args.cohort),None) or args.cohort or 'specified cohort'
        if not args.cohort and not args.tag_path:
            raise ValueError('Choose a cohort card or give its exact tag path and districts.')
        if args.cohort:
            cards=(plan.summary or {}).get('cohort_cards',[])
            leaves=(plan.summary or {}).get('cohort_model',{}).get('leaves',[])
            cohort=next((c for c in cards+leaves if c['id']==args.cohort),None)
            if cohort is None:raise ValueError('Choose a cohort from the current plan.')
            request=OverrideRequest(tag_path=cohort['tag_path'],districts=cohort['districts'],type=args.type,value=args.value,note=args.note)
        else:
            request=OverrideRequest(tag_path=args.tag_path,districts=args.districts,type=args.type,value=args.value,note=args.note)
        result=change_context(session,plan,request,source='chat')
        result=_visible_edit(result)
        action={'type':'edit','label':label,**result}
        return clean({**result,'label':label,'applied':True}),clean(action)
    if name=='undo_edit':
        from ..api.cohorts import undo_context
        result=_visible_edit(undo_context(session,plan,args.edit_id))
        return clean({**result,'applied':True}),clean({'type':'undo','label':'Context edit undone','edit_id':args.edit_id,**result})
    if name=='bulk_edit_orders':
        from ..api.cohorts import BulkOrderRequest,bulk_edit_orders
        result=_visible_edit(bulk_edit_orders(session,plan,BulkOrderRequest.model_validate(args.model_dump()),source='chat'))
        return clean({**result,'applied':True}),clean({'type':'edit','label':'Order quantities updated',**result})
    if name=='set_goal':
        from ..api.cohorts import change_goal
        result=_visible_edit(change_goal(session,plan,args.goal,args.service_level,source='chat'))
        return clean({**result,'applied':True}),clean({'type':'edit','label':'Buying objective updated',**result})
    if name=='add_watch':
        scope=_scope(session,args)
        if args.kind in {'capacity','days_cover'} and args.districts:raise ValueError('Use fill rate for district-specific shortages; warehouse stock is shared.')
        wid=add_watch(session,plan,WatchEdit(kind=args.kind,title=args.title,assumption=args.assumption,scope=scope),origin='chat')
        result={'id':wid,'title':args.title,'scope':scope,'applied':True}
        return result,{'type':'watch',**result}
    raise ValueError('Unsupported planning tool.')


def _visible_edit(result):
    """Keep full snapshots in Decision; send only the visible diff to the agent."""
    affected={row['sku'] for row in result.get('affected_orders',[])}
    visible={k:v for k,v in result.items() if k not in {'before','after'}}
    for key in ('before','after'):
        snapshot=result.get(key,{})
        visible[key]={k:snapshot[k] for k in ('stage','goal','service_level','overrides') if k in snapshot}
        visible[key]['orders']=[{'sku':row['sku'],'cases':row['final_cases'] if row['final_cases'] is not None else max(0,row['suggested_cases']-row['capacity_cut_cases']),'factor':row['adjustment']} for row in snapshot.get('orders',[]) if row['sku'] in affected]
    return visible
