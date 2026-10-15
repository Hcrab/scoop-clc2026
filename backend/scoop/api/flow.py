"""Five visible views, independent of the internal order drafting status."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Literal
from sqlalchemy import select

from ..db import session_scope
from ..models import SimulationRun
from .. import simulation_jobs
from .service import plan_for

router = APIRouter(prefix='/api')
STEPS = ('report', 'orders', 'watch', 'play', 'results')
FALLBACK = {'discover': 'report', 'direction': 'orders', 'execute': 'watch', 'closed': 'results'}
EDIT_NOTICE = 'Orders changed. Review the updated list.'


def state(session, plan):
    saved = (plan.summary or {}).get('flow') or {}
    initial = FALLBACK.get(plan.stage, 'report')
    step = saved.get('step', initial)
    maximum = saved.get('max_step', initial)
    if step not in STEPS or maximum not in STEPS:
        step = maximum = initial
    if STEPS.index(step) > STEPS.index(maximum):
        step = maximum
    return {'step': step, 'max_step': maximum,
            'order_hash': simulation_jobs.order_hash(session, plan),
            'notice': saved.get('notice')}


def save(plan, step, maximum, notice=None):
    plan.summary = {**(plan.summary or {}), 'flow':
                    {'step': step, 'max_step': maximum, 'notice': notice}}


def invalidate(session, plan):
    from ..db import schedule_simulation_after_commit
    previously_approved = plan.stage in {'execute', 'closed'} or bool((plan.summary or {}).get('approved_capacity'))
    if not previously_approved:
        previously_approved = session.scalar(select(SimulationRun.plan_id).where(
            SimulationRun.plan_id == plan.id).limit(1)) is not None
    if previously_approved:
        save(plan, 'orders', 'orders', EDIT_NOTICE)
        schedule_simulation_after_commit(session, plan.id)


class FlowRequest(BaseModel):
    step: Literal['report', 'orders', 'watch', 'play', 'results']


@router.get('/plans/{pid}/simulation')
def simulation_status(pid: str):
    with session_scope() as session:
        plan = plan_for(session, pid)
        return simulation_jobs.status(session, plan)


@router.post('/plans/{pid}/simulation')
def retry_simulation(pid: str):
    with session_scope() as session:
        plan_for(session, pid)
    return simulation_jobs.enqueue(pid, retry=True)


@router.put('/plans/{pid}/flow')
def set_flow(pid: str, body: FlowRequest):
    with session_scope() as session:
        plan = plan_for(session, pid)
        current = state(session, plan)
        maximum = current['max_step']
        if body.step == 'play' and maximum == 'watch':
            maximum = 'play'
        if STEPS.index(body.step) > STEPS.index(maximum):
            raise HTTPException(409, 'Complete the preceding step first.')
        save(plan, body.step, maximum, current['notice'])
        return {**current, 'step': body.step, 'max_step': maximum}


@router.post('/plans/{pid}/play-complete')
def play_complete(pid: str):
    with session_scope() as session:
        plan = plan_for(session, pid)
        current = state(session, plan)
        if current['step'] != 'play':
            raise HTTPException(409, 'Enter Play first.')
        run = session.get(SimulationRun, (pid, current['order_hash']))
        if run is None or run.status != 'ready':
            raise HTTPException(409, 'Replay is still preparing.')
        save(plan, 'play', 'results', current['notice'])
        return {**current, 'max_step': 'results'}
