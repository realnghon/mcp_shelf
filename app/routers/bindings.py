from fastapi import APIRouter, HTTPException, Query

from app.schemas.binding import BindingCreate, BindingUpdate, BindingCapabilityAdd
from app.schemas.common import PaginatedResponse
from app.services.binding_service import BindingService

router = APIRouter()
svc = BindingService()


@router.get("", response_model=PaginatedResponse)
async def list_bindings(
    visibility: str | None = None,
    search: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    items, total = await svc.list_bindings(
        visibility=visibility, search=search, page=page, page_size=page_size,
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("", status_code=201)
async def create_binding(data: BindingCreate):
    return await svc.create_binding(data)


@router.get("/{binding_id}")
async def get_binding(binding_id: str):
    binding = await svc.get_binding(binding_id)
    if not binding:
        raise HTTPException(404, "Binding not found")
    return binding


@router.put("/{binding_id}")
async def update_binding(binding_id: str, data: BindingUpdate):
    binding = await svc.update_binding(binding_id, data)
    if not binding:
        raise HTTPException(404, "Binding not found")
    return binding


@router.delete("/{binding_id}", status_code=204)
async def delete_binding(binding_id: str):
    ok = await svc.delete_binding(binding_id)
    if not ok:
        raise HTTPException(404, "Binding not found")


@router.post("/{binding_id}/capabilities")
async def add_capability(binding_id: str, data: BindingCapabilityAdd):
    try:
        return await svc.add_capability(binding_id, data)
    except Exception as e:
        raise HTTPException(400, str(e))


@router.delete("/{binding_id}/capabilities/{capability_id}", status_code=204)
async def remove_capability(binding_id: str, capability_id: str):
    ok = await svc.remove_capability(binding_id, capability_id)
    if not ok:
        raise HTTPException(404, "Capability not found in binding")


@router.post("/{binding_id}/clone")
async def clone_binding(binding_id: str):
    binding = await svc.clone_binding(binding_id)
    if not binding:
        raise HTTPException(404, "Binding not found")
    return binding
