"""Read-only default tour source identity."""
from fastapi import APIRouter, HTTPException
from ..tour_bundle import source_identity
router = APIRouter(prefix='/api/tour')

@router.get('/source')
def source():
    try:
        return source_identity()
    except ValueError as exc:
        raise HTTPException(503, str(exc)) from exc
