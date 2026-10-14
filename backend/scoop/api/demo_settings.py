from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,ConfigDict
from ..demo_worlds import manager,WorldPreparationError
from ..demo_gate import DemoBusy

router=APIRouter(prefix='/api/demo-settings')
class SelectWorld(BaseModel):
    model_config=ConfigDict(extra='forbid')
    scenario_id:str
    week_start:str
@router.get('')
def settings(): return manager.info()
def prepare(body,reset=False):
    try: return manager.choose(body.scenario_id,body.week_start,reset=reset)
    except ValueError as exc: raise HTTPException(422,str(exc)) from exc
    except (DemoBusy,WorldPreparationError) as exc: raise HTTPException(503,str(exc)) from exc
@router.post('/select')
def select(body:SelectWorld): return prepare(body)
@router.post('/reset')
def reset(body:SelectWorld): return prepare(body,reset=True)
