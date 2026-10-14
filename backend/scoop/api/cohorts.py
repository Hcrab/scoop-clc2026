"""Planner context API shared by UI and agent tools."""
from copy import deepcopy
from datetime import date, datetime
from typing import Any, Literal
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, delete

from . import service
from ..cohort_context import load_overrides, put_override, save_overrides
from ..models import PurchaseSuggestion, Store, Product, WatchItem, Decision

router = APIRouter(prefix='/api')


class OverrideRequest(BaseModel):
    cohort: str | None = None
    tag_path: list[dict] = Field(default_factory=list)
    districts: list[str] = Field(default_factory=list)
    type: Literal['one_off', 'ends_on', 'cap', 'expect', 'cases']
    value: Any = None
    note: str = ''
    expires_on: str | None = None


def order_snapshot(session, plan):
    return [service.row(x) for x in service.objects(session, PurchaseSuggestion, plan.id)]


def effective(row):
    return row['final_cases'] if row['final_cases'] is not None else max(0, row['suggested_cases']-row['capacity_cut_cases'])


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
    before = {'overrides': load_overrides(session), 'orders': order_snapshot(session, plan),
              'summary': deepcopy(plan.summary), 'stage': plan.stage,
              'locked_at': plan.locked_at.isoformat() if plan.locked_at else None,
              'watches':[service.row(x) for x in service.objects(session, WatchItem, plan.id)]}
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
    after_orders = order_snapshot(session, plan)
    old = {x['sku']: x for x in before['orders']}
    changed = [{'sku': x['sku'], 'before': effective(old[x['sku']]) if x['sku'] in old else 0,
                'after': effective(x), 'factor_before': old.get(x['sku'], {}).get('adjustment', 1.),
                'factor_after': x['adjustment']} for x in after_orders
               if x['sku'] not in old or effective(x) != effective(old[x['sku']]) or x['adjustment'] != old[x['sku']]['adjustment']]
    after = {'overrides': load_overrides(session), 'orders': after_orders, 'stage': plan.stage,
             'watches':[service.row(x) for x in service.objects(session, WatchItem, plan.id)]}
    result = {'override': stored, 'before': before, 'after': after, 'affected_orders': changed}
    edit = Decision(plan_id=plan.id,stage=plan.stage,key='set_override',value=service.clean(result),
                    source=source,created_at=datetime.now())
    session.add(edit)
    session.flush()
    return {**result, 'edit_id':edit.id}


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
        orders = suggest_orders(plan.week_start, [], goal=plan.goal, service_level=plan.service_level,
                                overrides=load_overrides(session, plan.week_start))
        cards = plan_cohort_cards(plan.week_start, orders, plan.goal, plan.service_level)
        plan.summary = {**(plan.summary or {}), 'cohort_model': orders.attrs['cohort_model'],
                        'cohort_cards': cards}
        return service.clean({'cards':cards,'method':orders.attrs['cohort_model']['method'],
                              'overrides':load_overrides(session, plan.week_start)})


def undo_context(session, plan, edit_id):
    edit = session.get(Decision, edit_id)
    if edit is None or edit.plan_id != plan.id or edit.key != 'set_override':
        raise HTTPException(404, 'Edit not found')
    value = edit.value
    if value.get('undone_at'):
        return {'edit_id':edit.id,'undone':True,'affected_orders':[]}
    before, after = value['before'], value['after']
    if order_snapshot(session,plan) != after['orders'] or load_overrides(session) != after['overrides']:
        raise HTTPException(409, 'Later order or context edits exist. Undo those changes first.')
    current_watches = [service.row(x) for x in service.objects(session, WatchItem, plan.id)]
    if current_watches != after['watches']:
        raise HTTPException(409, 'Watch changes were made after this edit. Restore those changes before undoing it.')
    save_overrides(session, before['overrides'])
    session.execute(delete(PurchaseSuggestion).where(PurchaseSuggestion.plan_id == plan.id))
    session.execute(delete(WatchItem).where(WatchItem.plan_id == plan.id))
    for data in before['orders']:
        row = dict(data)
        row['order_date'] = date.fromisoformat(row['order_date'])
        session.add(PurchaseSuggestion(**row))
    for data in before['watches']:
        session.add(WatchItem(**data))
    plan.summary = deepcopy(before['summary'])
    plan.stage = before['stage']
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
