"""Small single-process gate for world replacement and ongoing assistant workers."""
from contextlib import contextmanager
from threading import Condition,get_ident
import time

class DemoBusy(RuntimeError): pass

class ActivityGate:
    def __init__(self):
        self.condition=Condition();self.readers=0;self.waiting=False;self.writer=None
    @contextmanager
    def activity(self,http=False):
        with self.condition:
            if self.writer==get_ident():
                owned=True
            else:
                owned=False
                if http and (self.waiting or self.writer is not None): raise DemoBusy('A simulation is being prepared. Please try again shortly.')
                # Existing HTTP workers may start nested DB sessions while a writer waits.
                while self.writer is not None: self.condition.wait()
                self.readers+=1
        try: yield
        finally:
            if not owned:
                with self.condition: self.readers-=1;self.condition.notify_all()
    @contextmanager
    def replacement(self,timeout=180):
        deadline=time.monotonic()+timeout
        with self.condition:
            if self.waiting or self.writer is not None: raise DemoBusy('Another simulation change is already being prepared.')
            self.waiting=True
            while self.readers:
                remaining=deadline-time.monotonic()
                if remaining<=0:
                    self.waiting=False;self.condition.notify_all();raise DemoBusy('The assistant is still finishing its current request. Try again shortly.')
                self.condition.wait(remaining)
            self.waiting=False;self.writer=get_ident()
        try: yield
        finally:
            with self.condition: self.writer=None;self.condition.notify_all()

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
            with self.gate.activity(http=True):
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
