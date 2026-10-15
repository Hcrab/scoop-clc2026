"""Source replacement waits for all work; planning reset waits for mutations."""
from contextlib import contextmanager
from threading import Condition,get_ident
from contextvars import ContextVar
import time

class DemoBusy(RuntimeError): pass

class ActivityGate:
    def __init__(self):
        self.condition=Condition();self.readers=0;self.mutators=0;self.waiting=False;self.writer=None
        self.planning_only=False
        self.read_only=ContextVar('scoop_read_only_activity',default=False)
    @contextmanager
    def activity(self,http=False,read_only=None):
        read_only=self.read_only.get() if read_only is None else read_only
        with self.condition:
            if self.writer==get_ident():
                owned=True
            else:
                owned=False
                blocked=(self.waiting or self.writer is not None) and not (self.planning_only and read_only)
                if http and blocked: raise DemoBusy('A simulation is being prepared. Please try again shortly.')
                # Existing HTTP workers may start nested DB sessions while a writer waits.
                while self.writer is not None and not (self.planning_only and read_only): self.condition.wait()
                self.readers+=1
                if not read_only:self.mutators+=1
        token=self.read_only.set(read_only)
        try: yield
        finally:
            self.read_only.reset(token)
            if not owned:
                with self.condition:
                    self.readers-=1
                    if not read_only:self.mutators-=1
                    self.condition.notify_all()
    @contextmanager
    def replacement(self,timeout=180,planning_only=False):
        deadline=time.monotonic()+timeout
        with self.condition:
            if self.waiting or self.writer is not None: raise DemoBusy('Another simulation change is already being prepared.')
            self.waiting=True;self.planning_only=planning_only
            while (self.mutators if planning_only else self.readers):
                remaining=deadline-time.monotonic()
                if remaining<=0:
                    self.waiting=False;self.planning_only=False;self.condition.notify_all();raise DemoBusy('The assistant is still finishing its current request. Try again shortly.')
                self.condition.wait(remaining)
            self.waiting=False;self.writer=get_ident()
        try: yield
        finally:
            with self.condition: self.writer=None;self.planning_only=False;self.condition.notify_all()

gate=ActivityGate()

class DemoGateMiddleware:
    def __init__(self,app,manager=None,activity_gate=None):
        self.app=app;self.manager=manager;self.gate=activity_gate or gate
    async def __call__(self,scope,receive,send):
        if scope['type']!='http': return await self.app(scope,receive,send)
        from starlette.responses import JSONResponse
        path=scope.get('path','')
        if path in {'/api/demo-settings/select','/api/demo-settings/reset'}: return await self.app(scope,receive,send)
        try:
            with self.gate.activity(http=True,read_only=scope.get('method') in {'GET','HEAD','OPTIONS'}):
                # Reports are from the seed42 experiment, never relabelled as seed73.
                if self.manager and path=='/api/evaluation' and self.manager.active_seed()!=42:
                    return await JSONResponse({'status':'pending','seed':self.manager.active_seed()})(scope,receive,send)
                if self.manager and path=='/api/bootstrap' and self.manager.active_seed()!=42:
                    import json
                    buffered=[]
                    async def capture(message): buffered.append(message)
                    await self.app(scope,receive,capture)
                    start=next((m for m in buffered if m['type']=='http.response.start'),None)
                    if start and start['status']==200:
                        body=b''.join(m.get('body',b'') for m in buffered if m['type']=='http.response.body')
                        data=json.loads(body);data['evaluation']=None
                        data.setdefault('metadata',{})['evaluation_provenance']='The available evaluation belongs to simulation seed42.'
                        output=json.dumps(data,ensure_ascii=False,allow_nan=False).encode()
                        start['headers']=[(k,v) for k,v in start['headers'] if k.lower()!=b'content-length']+[(b'content-length',str(len(output)).encode())]
                        await send(start);return await send({'type':'http.response.body','body':output})
                    for message in buffered: await send(message)
                    return
                return await self.app(scope,receive,send)
        except DemoBusy as exc: return await JSONResponse({'detail':str(exc)},status_code=503,headers={'Retry-After':'2'})(scope,receive,send)
