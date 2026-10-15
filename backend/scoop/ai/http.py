"""Actual assistant progress events; final responses are emitted after commit."""
from datetime import datetime
from contextvars import copy_context
import json
import logging
from queue import Empty,Queue
from threading import Thread
from typing import Literal

from fastapi import APIRouter,HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel,ConfigDict,Field,field_validator

from ..models import ChatMessage,Finding,Product
from .chat import respond

router=APIRouter(prefix='/api')
logger=logging.getLogger(__name__)


class Focus(BaseModel):
    model_config=ConfigDict(extra='forbid')
    finding_id:str|None=Field(default=None,max_length=120)
    sku:str|None=Field(default=None,max_length=80)


class ChatRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    message:str=Field(min_length=1,max_length=4000)
    stage:Literal['discover','direction','execute']
    context:Focus=Field(default_factory=Focus)

    @field_validator('message')
    @classmethod
    def meaningful(cls,value):
        if not value.strip():raise ValueError('Enter a question or request.')
        return value.strip()


def answer(session,plan,body,progress=None):
    focus=body.context.model_dump(exclude_none=True)
    if focus.get('finding_id'):
        finding=session.get(Finding,focus['finding_id'])
        if not finding or finding.plan_id!=plan.id:raise HTTPException(422,'The selected finding is not in this plan.')
    if focus.get('sku') and not session.get(Product,focus['sku']):raise HTTPException(422,'The selected product is not in the catalog.')
    result=respond(session,plan,body.message,body.stage,focus,progress)
    metadata={'provider':result.provider,'actions':result.actions,'tool_trace':result.tool_trace,'usage':result.usage}
    if result.fallback_reason:metadata['fallback_reason']=result.fallback_reason
    session.add(ChatMessage(plan_id=plan.id,stage=body.stage,role='user',content=body.message,meta={'provider':result.provider,'context':focus},created_at=datetime.now()))
    session.add(ChatMessage(plan_id=plan.id,stage=body.stage,role='assistant',content=result.reply,meta=metadata,created_at=datetime.now()))
    from ..discussion import view
    return {'reply':result.reply,**metadata,'discussion':view(session,plan)}


@router.post('/plans/{pid}/chat/stream')
def stream_chat(pid:str,body:ChatRequest):
    from ..api import service
    from ..demo_gate import gate
    events=Queue()
    def work():
        try:
            with service.session_scope() as session:
                plan=service.plan_for(session,pid)
                result=answer(session,plan,body,lambda payload:events.put(('progress',payload)))
            # The transaction has committed before the browser sees success.
            events.put(('result',service.clean(result)))
        except HTTPException as exc:
            events.put(('error',{'detail':str(exc.detail),'status':exc.status_code}))
        except Exception as exc:
            logger.error('Assistant request failed (%s)',type(exc).__name__)
            events.put(('error',{'detail':'The response could not be saved. No partial plan change was committed. Please try again.','status':503}))
        finally:
            worker_lease.__exit__(None,None,None)
            events.put(('done',{}))

    def stream():
        # Reserve activity before starting the thread so disconnects cannot let
        # a simulation switch overtake a not-yet-scheduled assistant worker.
        nonlocal worker_lease
        worker_lease=gate.activity()
        worker_context=copy_context()
        worker_context.run(worker_lease.__enter__)
        try: Thread(target=worker_context.run,args=(work,),daemon=True,name='scoop-assistant').start()
        except BaseException:
            worker_context.run(worker_lease.__exit__,None,None,None)
            raise
        while True:
            try:kind,payload=events.get(timeout=10)
            except Empty:
                yield ': connection open\n\n'
                continue
            if kind=='done':break
            yield 'event: '+kind+'\ndata: '+json.dumps(payload,ensure_ascii=False)+'\n\n'
    worker_lease=None
    return StreamingResponse(stream(),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})
