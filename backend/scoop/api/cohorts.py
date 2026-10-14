"""Planner context API shared by UI and agent tools."""
from copy import deepcopy
from typing import Any, Literal
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from . import service
from ..cohort_context import load_overrides, put_override, save_overrides
from ..models import PurchaseSuggestion, Store, Product

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
              'summary': deepcopy(plan.summary), 'stage': plan.stage}
    try:
        _, _, stored = put_override(session, payload)
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(422, str(exc)) from exc
    session.flush()
    service.recompute(session, plan)
    if plan.stage == 'execute':
        plan.stage = 'direction'
    session.flush()
    after_orders = order_snapshot(session, plan)
    old = {x['sku']: x for x in before['orders']}
    changed = [{'sku': x['sku'], 'before': effective(old[x['sku']]) if x['sku'] in old else 0,
                'after': effective(x), 'factor_before': old.get(x['sku'], {}).get('adjustment', 1.),
                'factor_after': x['adjustment']} for x in after_orders
               if x['sku'] not in old or effective(x) != effective(old[x['sku']]) or x['adjustment'] != old[x['sku']]['adjustment']]
    after = {'overrides': load_overrides(session), 'orders': after_orders, 'stage': plan.stage}
    result = {'override': stored, 'before': before, 'after': after, 'affected_orders': changed}
    service.decision(session, plan, 'set_override', result, source)
    return result


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
