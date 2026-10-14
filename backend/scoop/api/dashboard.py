"""Shared dashboard API for the UI and conversational tools."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from . import service
from .cohorts import edit_snapshot, record_edit
from .. import dashboard
from ..models import WatchItem

router = APIRouter(prefix='/api/plans/{pid}')


class Scope(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: str
    key: str = ''


class Threshold(BaseModel):
    model_config = ConfigDict(extra='forbid')
    operator: str
    value: float = Field(allow_inf_nan=False)


class WidgetSpec(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str
    scope: Scope
    metric: str
    threshold: Threshold | None = None


class Layout(BaseModel):
    ids: list[str]


def _plan(session, pid):
    return service.plan_for(session, pid)


def _widget(session, plan, wid):
    item = session.get(WatchItem, wid)
    if not item or item.plan_id != plan.id or item.status != 'active' or not isinstance(item.scope, dict) or 'metric' not in item.scope:
        raise HTTPException(404, 'Widget not found')
    return item


def _result(session, plan, before, key, source='ui'):
    result = record_edit(session, plan, before, key, source)
    return service.clean({**result, **dashboard.view(session, plan)})


def add(session, plan, spec, source='ui'):
    canonical = dashboard.canonical(spec)
    dashboard.resolve(session, plan, canonical)
    dashboard.initialize(session, plan)
    before = edit_snapshot(session, plan)
    widget = dashboard.save(session, plan, canonical, origin='chat' if source == 'chat' else 'decision')
    plan.summary = {**(plan.summary or {}), 'dashboard_order': [*(plan.summary or {}).get('dashboard_order', []), widget.id]}
    return _result(session, plan, before, 'dashboard_add', source)


def update(session, plan, wid, spec, source='ui'):
    dashboard.initialize(session, plan)
    item = _widget(session, plan, wid)
    canonical = dashboard.canonical(spec)
    dashboard.resolve(session, plan, canonical)
    duplicate = session.scalar(select(WatchItem).where(WatchItem.plan_id == plan.id, WatchItem.title == canonical['title'], WatchItem.id != wid))
    if duplicate: raise HTTPException(422, 'Widget title already exists')
    before = edit_snapshot(session, plan)
    item.title = canonical['title']; item.kind = 'req_vs_expected' if canonical['metric'] == 'requested_vs_expected' else canonical['metric']; item.scope = canonical
    session.flush()
    return _result(session, plan, before, 'dashboard_update', source)


def remove(session, plan, wid, source='ui'):
    dashboard.initialize(session, plan)
    item = _widget(session, plan, wid)
    before = edit_snapshot(session, plan)
    # A tombstone releases the unique title for later reuse without losing undo data.
    item.status = 'archived'
    item.title = ('~' + item.id + ' ' + item.title)[:160]
    plan.summary = {**(plan.summary or {}), 'dashboard_order': [x for x in plan.summary['dashboard_order'] if x != wid]}
    session.flush()
    return _result(session, plan, before, 'dashboard_remove', source)


def layout(session, plan, ids, source='ui'):
    dashboard.initialize(session, plan)
    active = {w.id for w in dashboard.active(session, plan)}
    if len(ids) != len(active) or set(ids) != active:
        raise HTTPException(422, 'Layout must contain each active widget exactly once')
    before = edit_snapshot(session, plan)
    plan.summary = {**(plan.summary or {}), 'dashboard_order': ids}
    return _result(session, plan, before, 'dashboard_layout', source)


@router.get('/dashboard')
def get_dashboard(pid: str):
    with service.session_scope() as session:
        return service.clean(dashboard.view(session, _plan(session, pid)))


@router.post('/dashboard')
def add_dashboard(pid: str, spec: WidgetSpec):
    with service.session_scope() as session:
        return add(session, _plan(session, pid), spec.model_dump())


@router.put('/dashboard/{wid}')
def update_dashboard(pid: str, wid: str, spec: WidgetSpec):
    with service.session_scope() as session:
        return update(session, _plan(session, pid), wid, spec.model_dump())


@router.delete('/dashboard/{wid}')
def remove_dashboard(pid: str, wid: str):
    with service.session_scope() as session:
        return remove(session, _plan(session, pid), wid)


@router.put('/dashboard-layout')
def update_layout(pid: str, data: Layout):
    with service.session_scope() as session:
        return layout(session, _plan(session, pid), data.ids)


@router.post('/dashboard-preview')
def preview(pid: str, spec: WidgetSpec):
    with service.session_scope() as session:
        return service.clean(dashboard.evaluate(session, _plan(session, pid), spec.model_dump()))
