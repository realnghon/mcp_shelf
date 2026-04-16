from fastapi import APIRouter, HTTPException, Query

from app.schemas.capability import CapabilityCreate, CapabilityUpdate, CapabilityOut, CapabilityVersionOut, CapabilityVersionCreate
from app.schemas.common import PaginatedResponse
from app.services.capability_test_service import CapabilityTestService
from app.services.capability_validation_service import CapabilityValidationService
from app.services.registry_service import RegistryService

router = APIRouter()
svc = RegistryService()
validation_svc = CapabilityValidationService()
test_svc = CapabilityTestService()


@router.get("", response_model=PaginatedResponse)
async def list_capabilities(
    kind: str | None = None,
    status: str | None = None,
    category: str | None = None,
    search: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    items, total = await svc.list_capabilities(
        kind=kind, status=status, category=category, search=search,
        page=page, page_size=page_size,
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("", status_code=201)
async def create_capability(data: CapabilityCreate):
    try:
        return await svc.create_capability(data)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/{cap_id}")
async def get_capability(cap_id: str):
    cap = await svc.get_capability(cap_id)
    if not cap:
        raise HTTPException(404, "Capability not found")
    return cap


@router.put("/{cap_id}")
async def update_capability(cap_id: str, data: CapabilityUpdate):
    cap = await svc.update_capability(cap_id, data)
    if not cap:
        raise HTTPException(404, "Capability not found")
    return cap


@router.delete("/{cap_id}", status_code=204)
async def delete_capability(cap_id: str):
    ok = await svc.delete_capability(cap_id)
    if not ok:
        raise HTTPException(404, "Capability not found")


@router.post("/{cap_id}/activate")
async def activate_capability(cap_id: str):
    cap = await svc.activate(cap_id)
    if not cap:
        raise HTTPException(404, "Capability not found")
    return cap


@router.post("/{cap_id}/deactivate")
async def deactivate_capability(cap_id: str):
    cap = await svc.deactivate(cap_id)
    if not cap:
        raise HTTPException(404, "Capability not found")
    return cap


@router.post("/{cap_id}/healthcheck")
async def healthcheck_capability(cap_id: str):
    from app.services.healthcheck_service import HealthcheckService
    hs = HealthcheckService()
    try:
        return await hs.check_capability(cap_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/{cap_id}/versions")
async def list_versions(cap_id: str):
    return await svc.list_versions(cap_id)


@router.post("/{cap_id}/versions", status_code=201)
async def create_version(cap_id: str, data: CapabilityVersionCreate):
    try:
        return await svc.create_version(cap_id, data.changelog)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/{cap_id}/test")
async def test_capability(cap_id: str, payload: dict):
    request_payload = payload.get("request_payload") or {}
    try:
        return await test_svc.run_test(cap_id, request_payload)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/{cap_id}/tests")
async def list_capability_tests(cap_id: str, limit: int = Query(10, ge=1, le=100)):
    try:
        return await test_svc.list_tests(cap_id, limit)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/validate")
async def validate_capability(config: dict):
    try:
        return await validation_svc.validate_capability(config)
    except ValueError as e:
        raise HTTPException(404, str(e))
