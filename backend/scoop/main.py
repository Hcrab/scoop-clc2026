"""Local Scoop application. Model training occurs only when a plan is requested."""
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from .api.service import router
from .api.cohorts import router as cohort_router
from .api.dashboard import router as dashboard_router
from .ai.http import router as assistant_router
from .config import ROOT
from .api.demo_settings import router as demo_router
from .demo_gate import DemoGateMiddleware
from .demo_worlds import manager

app=FastAPI(title='Scoop synthetic warehouse planner')
app.include_router(router)
app.include_router(cohort_router)
app.include_router(dashboard_router)
app.include_router(assistant_router)
app.include_router(demo_router)
app.add_middleware(DemoGateMiddleware,manager=manager)

@app.get('/health')
def health():
    from .ai.chat import provider_info
    return {'status':'ok','synthetic':True,**provider_info()}

@app.get('/{path:path}',include_in_schema=False)
def frontend(path:str):
    if path=='api' or path.startswith('api/'): raise HTTPException(404,'API route not found')
    dist=(ROOT/'frontend'/'dist').resolve()
    file=(dist/path).resolve()
    if not file.is_relative_to(dist): raise HTTPException(404,'Not found')
    if file.is_file(): return FileResponse(file)
    if (dist/'index.html').exists(): return FileResponse(dist/'index.html')
    raise HTTPException(404,'Frontend build is not available yet')
