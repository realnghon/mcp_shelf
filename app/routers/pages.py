"""Page routes - serve Jinja2 rendered HTML pages."""

from fastapi import APIRouter, Request

from app.core.config import settings
from app.core.templates import get_templates
from app.runtime.adapters.local_tools import get_local_tool_catalog
from app.services.binding_service import BindingService
from app.services.llm_config_service import LLMConfigService
from app.services.registry_service import RegistryService
from app.services.session_service import SessionService

router = APIRouter()
templates = get_templates()
reg_svc = RegistryService()
bind_svc = BindingService()
sess_svc = SessionService()
llm_svc = LLMConfigService()


@router.get("/")
async def index(request: Request):
    bindings, _ = await bind_svc.list_bindings(page_size=100)
    sessions, _ = await sess_svc.list_sessions(page_size=50)
    capabilities, _ = await reg_svc.list_capabilities(page_size=100)
    capabilities = _merge_builtin_capabilities(capabilities)
    return templates.TemplateResponse("index.html", {
        "request": request,
        "bindings": bindings,
        "sessions": sessions,
        "capabilities": capabilities,
        "default_model": f"openai:{settings.openai_model}",
    })


@router.get("/capabilities")
async def capabilities_page(request: Request):
    items, total = await reg_svc.list_capabilities(page_size=100)
    return templates.TemplateResponse("capabilities/list.html", {
        "request": request,
        "capabilities": items,
        "total": total,
    })


@router.get("/capabilities/new")
async def new_capability_page(request: Request):
    return templates.TemplateResponse("capabilities/form.html", {
        "request": request,
        "capability": None,
    })


@router.get("/capabilities/{cap_id}/edit")
async def edit_capability_page(request: Request, cap_id: str):
    cap = await reg_svc.get_capability(cap_id)
    return templates.TemplateResponse("capabilities/form.html", {
        "request": request,
        "capability": cap,
    })


@router.get("/capabilities/{cap_id}")
async def capability_detail_page(request: Request, cap_id: str):
    cap = await reg_svc.get_capability(cap_id)
    if not cap:
        return templates.TemplateResponse("index.html", {"request": request, "error": "Not found"})
    versions = await reg_svc.list_versions(cap_id)
    return templates.TemplateResponse("capabilities/detail.html", {
        "request": request,
        "capability": cap,
        "versions": versions,
    })


@router.get("/bindings")
async def bindings_page(request: Request):
    items, total = await bind_svc.list_bindings(page_size=100)
    return templates.TemplateResponse("bindings/list.html", {
        "request": request,
        "bindings": items,
        "total": total,
    })


@router.get("/bindings/{binding_id}")
async def binding_detail_page(request: Request, binding_id: str):
    binding = await bind_svc.get_binding(binding_id)
    if not binding:
        return templates.TemplateResponse("index.html", {"request": request, "error": "Not found"})
    return templates.TemplateResponse("bindings/form.html", {
        "request": request,
        "binding": binding,
    })


@router.get("/playground")
async def playground_page(request: Request):
    """Redirect to home page which now has the chat interface."""
    from starlette.responses import RedirectResponse
    return RedirectResponse(url="/")


@router.get("/sessions/{session_id}/trace")
async def trace_page(request: Request, session_id: str):
    session = await sess_svc.get_session(session_id)
    messages = await sess_svc.list_messages(session_id) if session else []
    return templates.TemplateResponse("sessions/trace.html", {
        "request": request,
        "session": session,
        "messages": messages,
    })


@router.get("/settings")
async def settings_page(request: Request):
    configs = await llm_svc.list_configs()
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "llm_configs": configs,
    })


def _merge_builtin_capabilities(capabilities: list[dict]) -> list[dict]:
    by_slug = {cap.get("slug"): cap for cap in capabilities}
    merged: list[dict] = []

    for builtin in get_local_tool_catalog():
        existing = by_slug.get(builtin["slug"])
        if existing:
            existing["is_builtin"] = True
            merged.append(existing)
        else:
            merged.append(builtin)

    seen_ids = {cap.get("id") for cap in merged}
    for cap in capabilities:
        if cap.get("id") not in seen_ids:
            merged.append(cap)

    return merged
