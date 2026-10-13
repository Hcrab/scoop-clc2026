"""Local Scoop application. Model training occurs only when a plan is requested."""
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from .api.service import router
from .config import ROOT

app=FastAPI(title='Scoop synthetic warehouse planner')
app.include_router(router)

@app.get('/health')
def health(): return {'status':'ok','synthetic':True,'provider':'scripted'}

@app.get('/{path:path}',include_in_schema=False)
def frontend(path:str):
    if path=='api' or path.startswith('api/'): raise HTTPException(404,'API route not found')
    dist=(ROOT/'frontend'/'dist').resolve()
    file=(dist/path).resolve()
    if not file.is_relative_to(dist): raise HTTPException(404,'Not found')
    if file.is_file(): return FileResponse(file)
    if (dist/'index.html').exists(): return FileResponse(dist/'index.html')
    raise HTTPException(404,'Frontend build is not available yet')
