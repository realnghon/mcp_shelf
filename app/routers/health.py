from fastapi import APIRouter, Query

from app.services.healthcheck_service import HealthcheckService

router = APIRouter()
svc = HealthcheckService()


@router.get("/summary")
async def health_summary():
    return await svc.get_summary()


@router.get("/capabilities/{capability_id}")
async def capability_health(capability_id: str, limit: int = Query(10, ge=1, le=50)):
    return await svc.get_capability_history(capability_id, limit)
