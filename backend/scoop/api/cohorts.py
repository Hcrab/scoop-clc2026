"""Planner context API shared by UI and agent tools."""
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Literal
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, delete

from . import service
from ..cohort_context import load_overrides, put_override, save_overrides
from ..models import PurchaseSuggestion, Store, Product, WatchItem, Decision, StoreOrder

router = APIRouter(prefix='/api')


class OverrideRequest(BaseModel):
    cohort: str | None = None
    tag_path: list[dict] = Field(default_factory=list)
    districts: list[str] = Field(default_factory=list)
    type: Literal['one_off', 'ends_on', 'cap', 'expect', 'cases']
    value: Any = None
    note: str = ''
    expires_on: str | None = None


class OrderFilter(BaseModel):
    tag: str | None = None
    group: str | None = None
    cohort: str | None = None
    family: str | None = None
    brand: str | None = None
    district: str | None = None
    skus: list[str] = Field(default_factory=list)


class OrderChange(BaseModel):
    type: Literal['percent', 'set_cases', 'fit_capacity']
    value: Any


class BulkOrderRequest(BaseModel):
    filter: OrderFilter = Field(default_factory=OrderFilter)
    change: OrderChange


def order_snapshot(session, plan):
    return [service.row(x) for x in service.objects(session, PurchaseSuggestion, plan.id)]


def effective(row):
    return row['final_cases'] if row['final_cases'] is not None else max(0, row['suggested_cases']-row['capacity_cut_cases'])


def edit_snapshot(session, plan):
    return {'overrides': load_overrides(session), 'orders': order_snapshot(session, plan),
            'summary': deepcopy(plan.summary), 'stage': plan.stage,
            'goal': plan.goal, 'service_level': plan.service_level,
            'locked_at': plan.locked_at.isoformat() if plan.locked_at else None,
            'watches': [service.row(x) for x in service.objects(session, WatchItem, plan.id)]}


def record_edit(session, plan, before, key, source='ui', **extra):
    after = edit_snapshot(session, plan)
    old = {x['sku']: x for x in before['orders']}
    changed = [{'sku': x['sku'], 'before': effective(old[x['sku']]) if x['sku'] in old else 0,
                'after': effective(x), 'factor_before': old.get(x['sku'], {}).get('adjustment', 1.),
                'factor_after': x['adjustment']} for x in after['orders']
               if x['sku'] not in old or effective(x) != effective(old[x['sku']]) or x['adjustment'] != old[x['sku']]['adjustment']]
    result = {'before': before, 'after': after, 'affected_orders': changed, **extra}
    edit = Decision(plan_id=plan.id, stage=plan.stage, key=key, value=service.clean(result),
                    source=source, created_at=datetime.now())
    session.add(edit)
    session.flush()
    return {**result, 'edit_id': edit.id}


def _matching_skus(session, plan, criteria):
    from ..ai.exploration_tools import _groups
    catalog = {p.sku:p for p in session.scalars(select(Product))}
    selected = set(catalog)
    groups = _groups(session)
    for identifier in (criteria.tag, criteria.group):
        if identifier:
            if identifier not in groups: raise HTTPException(422, 'Unknown catalog group')
            selected &= set(groups[identifier].skus)
    if criteria.cohort:
        leaves = (plan.summary or {}).get('cohort_model', {}).get('leaves', [])
        cards = (plan.summary or {}).get('cohort_cards', [])
        cohort = next((x for x in cards+leaves if x['id']==criteria.cohort),None)
        if cohort is None:raise HTTPException(422,'Unknown plan cohort')
        selected &= set(cohort.get('skus',[]))
    if criteria.family:
        identifier=criteria.family
        if not identifier.startswith('family:') or identifier not in groups:raise HTTPException(422,'Unknown family')
        selected &= set(groups[identifier].skus)
    if criteria.brand:
        if criteria.brand not in {p.brand for p in catalog.values()}:raise HTTPException(422,'Unknown brand')
        selected &= {sku for sku,p in catalog.items() if p.brand==criteria.brand}
    if criteria.district:
        if criteria.district not in set(session.scalars(select(Store.district))):raise HTTPException(422,'Unknown district')
        units=(plan.summary or {}).get('cohort_model',{}).get('units',[])
        exposure={u['sku'] for u in units if u.get('district')==criteria.district}
        if not units:
            exposure=set(session.scalars(select(StoreOrder.sku).join(Store,Store.id==StoreOrder.store_id).where(Store.district==criteria.district,StoreOrder.date<plan.week_start)))
        selected &= exposure
    if criteria.skus:
        if set(criteria.skus)-set(catalog):raise HTTPException(422,'Unknown SKU')
        selected &= set(criteria.skus)
    selected &= {x.sku for x in service.objects(session,PurchaseSuggestion,plan.id)}
    if not selected:raise HTTPException(422,'No current orders match the selected filters')
    return sorted(selected)


def bulk_edit_orders(session, plan, request, source='ui'):
    from ..cohort_context import put_override
    from ..planning import suggest_orders, confirmation_capacity
    kind,value=request.change.type,request.change.value
    criteria=request.filter
    if kind=='percent':
        if type(value) not in (int,float) or not -100<=value<=1000:raise HTTPException(422,'Percent must be between -100 and 1000')
    elif kind=='set_cases':
        if type(value) is not int or value<0:raise HTTPException(422,'Cases must be a nonnegative integer')
    else:
        if type(value) not in (int,float) or not 0<value<=1:raise HTTPException(422,'Capacity value must be a fraction greater than 0 and at most 1')
        if any((criteria.tag,criteria.group,criteria.cohort,criteria.family,criteria.brand,criteria.district,criteria.skus)):
            raise HTTPException(422,'Capacity fit applies to the full plan; leave filters empty')
    selected=_matching_skus(session,plan,criteria) if kind!='fit_capacity' else [x.sku for x in service.objects(session,PurchaseSuggestion,plan.id)]
    before=edit_snapshot(session,plan)
    current={r['sku']:effective(r) for r in before['orders']}
    cases={}
    if kind=='percent':
        multiplier=Decimal('1')+Decimal(str(value))/100
        cases={sku:int((Decimal(current[sku])*multiplier).quantize(Decimal('1'),rounding=ROUND_HALF_UP)) for sku in selected}
    elif kind=='set_cases':cases={sku:value for sku in selected}
    else:
        from ..models import DirectionItem, Node
        capacity=session.get(Node,'DC1')
        if capacity is None:raise HTTPException(422,'Warehouse capacity unavailable')
        target=capacity.capacity_pallets*value
        directions=[service.row(d) for d in service.objects(session,DirectionItem,plan.id)]
        result=suggest_orders(plan.week_start,directions,service_level=plan.service_level,goal=plan.goal,
                              overrides=load_overrides(session,plan.week_start),capacity_limit=target,
                              apply_case_overrides=False,initial_cases=current)
        cases={r.sku:int(r.final_cases) for r in result.itertuples()}
    for sku,count in cases.items():
        put_override(session,{'tag_path':[],'districts':[],'type':'cases','value':{'sku':sku,'cases':count},'note':'Order quantity edit'})
    session.flush()
    service.recompute(session,plan)
    if plan.stage=='execute':plan.stage='direction';plan.locked_at=None
    session.flush()
    projection=confirmation_capacity(plan.week_start,{r['sku']:effective(r) for r in order_snapshot(session,plan)})
    capacity_summary={k:projection[k] for k in ('capacity_pallets','projected_peak_pallets','inherited_peak_pallets','incremental_overcapacity_pallets','feasible')}
    if kind=='fit_capacity':
        capacity_summary.update(target_fraction=value,target_pallets=target,
                                inherited_excess_pallets=max(0,projection['inherited_peak_pallets']-target),
                                target_met=projection['projected_peak_pallets']<=target+1e-8)
    return record_edit(session,plan,before,'bulk_edit_orders',source,filter=criteria.model_dump(),
                       change=request.change.model_dump(),capacity=capacity_summary)


def change_goal(session,plan,goal,service_level,source='ui'):
    before=edit_snapshot(session,plan)
    plan.goal=goal;plan.service_level=service_level
    service.recompute(session,plan)
    if plan.stage=='execute':plan.stage='direction';plan.locked_at=None
    session.flush()
    return record_edit(session,plan,before,'goal_edit',source,goal=goal,service_level=service_level)


@router.post('/plans/{pid}/orders/bulk')
def edit_orders(pid:str,body:BulkOrderRequest):
    with service.session_scope() as session:
        plan=service.plan_for(session,pid,['discover','direction','execute'])
        return service.clean(bulk_edit_orders(session,plan,body))


def change_context(session, plan, request, source='ui'):
    payload = request.model_dump()
    if request.cohort:
        leaves = (plan.summary or {}).get('cohort_model', {}).get('leaves', [])
        leaf = next((x for x in leaves if x['id'] == request.cohort), None)
        if leaf is None:
            raise HTTPException(404, 'Cohort not found')
        payload.update(tag_path=leaf['tag_path'], districts=leaf['districts'])
    from ..ai.exploration_tools import _groups
    groups = _groups(session)
    known_districts = set(session.scalars(select(Store.district)))
    for term in payload['tag_path']:
        identifier = term.get('id', '')
        if identifier not in groups and identifier not in {'district:'+d for d in known_districts}:
            raise HTTPException(422, 'Unknown cohort tag')
    if set(payload['districts']) - known_districts:
        raise HTTPException(422, 'Unknown district')
    if request.type == 'cases' and (not isinstance(request.value, dict) or not session.get(Product, request.value.get('sku'))):
        raise HTTPException(422, 'Unknown SKU')
    before = edit_snapshot(session, plan)
    try:
        _, _, stored = put_override(session, payload)
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(422, str(exc)) from exc
    session.flush()
    service.recompute(session, plan)
    if plan.stage == 'execute':
        plan.stage = 'direction'
        plan.locked_at = None
    session.flush()
    return record_edit(session, plan, before, 'set_override', source, override=stored)


@router.post('/plans/{pid}/overrides')
def set_override(pid: str, body: OverrideRequest):
    with service.session_scope() as session:
        plan = service.plan_for(session, pid, ['discover', 'direction', 'execute'])
        return change_context(session, plan, body)


@router.get('/plans/{pid}/overrides')
def get_overrides(pid: str):
    with service.session_scope() as session:
        plan = service.plan_for(session, pid)
        return load_overrides(session, plan.week_start)


@router.get('/plans/{pid}/cohorts')
def get_cohorts(pid: str):
    from ..planning import suggest_orders, plan_cohort_cards
    with service.session_scope() as session:
        plan = service.plan_for(session, pid)
        saved=plan.summary or {}
        if 'cohort_cards' in saved and 'cohort_model' in saved:
            return service.clean({'cards':saved['cohort_cards'],
                                  'method':saved['cohort_model'].get('method',{}),
                                  'overrides':load_overrides(session,plan.week_start)})
        orders = suggest_orders(plan.week_start, [], goal=plan.goal, service_level=plan.service_level,
                                overrides=load_overrides(session, plan.week_start))
        cards = plan_cohort_cards(plan.week_start, orders, plan.goal, plan.service_level)
        plan.summary = {**(plan.summary or {}), 'cohort_model': orders.attrs['cohort_model'],
                        'cohort_cards': cards}
        return service.clean({'cards':cards,'method':orders.attrs['cohort_model']['method'],
                              'overrides':load_overrides(session, plan.week_start)})


def undo_context(session, plan, edit_id):
    edit = session.get(Decision, edit_id)
    if edit is None or edit.plan_id != plan.id or edit.key not in {'set_override','bulk_edit_orders','goal_edit','dashboard_add','dashboard_update','dashboard_remove','dashboard_layout'}:
        raise HTTPException(404, 'Edit not found')
    value = edit.value
    if value.get('undone_at'):
        return {'edit_id':edit.id,'undone':True,'affected_orders':[]}
    before, after = value['before'], value['after']
    current = edit_snapshot(session,plan)
    if edit.key.startswith('dashboard_'):
        if current['watches'] != after['watches'] or (current['summary'] or {}).get('dashboard_order') != (after['summary'] or {}).get('dashboard_order'):
            raise HTTPException(409, 'Later dashboard edits exist. Undo those changes first.')
        session.execute(delete(WatchItem).where(WatchItem.plan_id == plan.id))
        for data in before['watches']:
            session.add(WatchItem(**data))
        summary = deepcopy(plan.summary or {})
        if 'dashboard_order' in (before['summary'] or {}):
            summary['dashboard_order'] = before['summary']['dashboard_order']
        else:
            summary.pop('dashboard_order', None)
        plan.summary = summary
        edit.value = {**value, 'undone_at': datetime.now().isoformat()}
        session.flush()
        return {'edit_id': edit.id, 'undone': True, 'before': after, 'after': before, 'affected_orders': []}
    # Read-time model/card refreshes and conversation do not edit the plan.
    derived = {'discussion', 'cohort_model', 'cohort_cards', 'weekly_review'}
    current_summary={k:v for k,v in (current['summary'] or {}).items() if k not in derived}
    after_summary={k:v for k,v in (after['summary'] or {}).items() if k not in derived}
    if {**current,'summary':current_summary} != {**after,'summary':after_summary}:
        raise HTTPException(409, 'Later plan edits exist. Undo those changes first.')
    save_overrides(session, before['overrides'])
    session.execute(delete(PurchaseSuggestion).where(PurchaseSuggestion.plan_id == plan.id))
    session.execute(delete(WatchItem).where(WatchItem.plan_id == plan.id))
    for data in before['orders']:
        row = dict(data)
        row['order_date'] = date.fromisoformat(row['order_date'])
        session.add(PurchaseSuggestion(**row))
    for data in before['watches']:
        session.add(WatchItem(**data))
    plan.summary = {**deepcopy(before['summary'] or {}),**({'discussion':current['summary']['discussion']} if current['summary'] and 'discussion' in current['summary'] else {})}
    plan.stage = before['stage']
    plan.goal = before['goal']
    plan.service_level = before['service_level']
    plan.locked_at = datetime.fromisoformat(before['locked_at']) if before['locked_at'] else None
    edit.value = {**value,'undone_at':datetime.now().isoformat()}
    return {'edit_id':edit.id,'undone':True,'before':after,'after':before,
            'affected_orders':[{'sku':x['sku'],'before':x['after'],'after':x['before'],
                                'factor_before':x['factor_after'],'factor_after':x['factor_before']}
                               for x in value['affected_orders']]}


@router.post('/plans/{pid}/edits/{edit_id}/undo')
def undo_edit(pid: str, edit_id: int):
    with service.session_scope() as session:
        plan = service.plan_for(session,pid,['discover','direction','execute'])
        return undo_context(session,plan,edit_id)
