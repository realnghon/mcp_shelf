from fastapi import APIRouter, Query

from app.schemas.common import PaginatedResponse
from app.services.audit_service import AuditService

router = APIRouter()
svc = AuditService()


@router.get("", response_model=PaginatedResponse)
async def list_audit(
    action: str | None = None,
    target_type: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    items, total = await svc.list_logs(
        action=action, target_type=target_type, page=page, page_size=page_size,
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/{target_type}/{target_id}")
async def target_audit(target_type: str, target_id: str):
    items, total = await svc.get_target_logs(target_type, target_id)
    return {"items": items, "total": total}
