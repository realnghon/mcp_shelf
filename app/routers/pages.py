"""Page routes - serve Jinja2 rendered HTML pages."""

from collections import Counter

from fastapi import APIRouter, Request

from app.core.config import settings
from app.core.templates import get_templates
from app.services.binding_service import BindingService
from app.services.capability_test_service import CapabilityTestService
from app.services.healthcheck_service import HealthcheckService
from app.services.llm_config_service import LLMConfigService
from app.services.registry_service import RegistryService
from app.services.session_service import SessionService

router = APIRouter()
templates = get_templates()
reg_svc = RegistryService()
bind_svc = BindingService()
sess_svc = SessionService()
health_svc = HealthcheckService()
test_svc = CapabilityTestService()
llm_svc = LLMConfigService()


@router.get("/")
async def index(request: Request):
    bindings, _ = await bind_svc.list_bindings(page_size=100)
    sessions, _ = await sess_svc.list_sessions(page_size=50)
    capabilities, _ = await reg_svc.list_capabilities(page_size=100, include_builtin=True)
    return templates.TemplateResponse(request, "index.html", {
        "request": request,
        "bindings": bindings,
        "sessions": sessions,
        "capabilities": capabilities,
        "default_model": f"openai:{settings.openai_model}",
    })


@router.get("/capabilities")
async def capabilities_page(
    request: Request,
    kind: str | None = None,
    status: str | None = None,
    category: str | None = None,
    search: str | None = None,
    sort_by: str = "updated_at",
    sort_order: str = "desc",
):
    items, total = await reg_svc.list_capabilities(
        page_size=100,
        include_builtin=True,
        kind=kind,
        status=status,
        category=category,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    all_items, _ = await reg_svc.list_capabilities(
        page_size=500,
        include_builtin=True,
        sort_by="name",
        sort_order="asc",
    )
    category_counter = Counter(
        (str(cap.get("category") or "uncategorized").strip() or "uncategorized")
        for cap in all_items
    )
    categories = [
        {"name": name, "count": count}
        for name, count in sorted(category_counter.items(), key=lambda pair: pair[0].lower())
    ]
    return templates.TemplateResponse(request, "capabilities/list.html", {
        "request": request,
        "capabilities": items,
        "total": total,
        "categories": categories,
        "all_total": len(all_items),
        "filters": {
            "kind": kind or "",
            "status": status or "",
            "category": category or "",
            "search": search or "",
            "sort_by": sort_by,
            "sort_order": sort_order,
        },
    })


@router.get("/capabilities/new")
async def new_capability_page(request: Request):
    return templates.TemplateResponse(request, "capabilities/form.html", {
        "request": request,
        "capability": None,
    })


@router.get("/capabilities/{cap_id}/edit")
async def edit_capability_page(request: Request, cap_id: str):
    cap = await reg_svc.get_capability(cap_id)
    return templates.TemplateResponse(request, "capabilities/form.html", {
        "request": request,
        "capability": cap,
    })


@router.get("/capabilities/{cap_id}")
async def capability_detail_page(request: Request, cap_id: str):
    cap = await reg_svc.get_capability(cap_id)
    if not cap:
        return templates.TemplateResponse(request, "index.html", {"request": request, "error": "Not found"})
    versions = [] if cap.get("is_builtin") else await reg_svc.list_versions(cap_id)
    test_history = await test_svc.list_tests(cap_id) if not cap.get("is_builtin") else []
    health_history = await health_svc.get_capability_history(cap_id)
    return templates.TemplateResponse(request, "capabilities/detail.html", {
        "request": request,
        "capability": cap,
        "versions": versions,
        "test_history": test_history,
        "health_history": health_history,
    })


@router.get("/bindings")
async def bindings_page(request: Request):
    items, total = await bind_svc.list_bindings(page_size=100)
    return templates.TemplateResponse(request, "bindings/list.html", {
        "request": request,
        "bindings": items,
        "total": total,
    })


@router.get("/bindings/new")
async def new_binding_page(request: Request):
    return templates.TemplateResponse(request, "bindings/form.html", {
        "request": request,
        "binding": None,
        "available_capabilities": [],
    })


@router.get("/bindings/{binding_id}")
async def binding_detail_page(request: Request, binding_id: str):
    binding = await bind_svc.get_binding(binding_id)
    if not binding:
        return templates.TemplateResponse(request, "index.html", {"request": request, "error": "Not found"})
    available_capabilities, _ = await reg_svc.list_capabilities(page_size=200, include_builtin=False)
    return templates.TemplateResponse(request, "bindings/form.html", {
        "request": request,
        "binding": binding,
        "available_capabilities": available_capabilities,
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
    return templates.TemplateResponse(request, "sessions/trace.html", {
        "request": request,
        "session": session,
        "messages": messages,
    })


@router.get("/settings")
async def settings_page(request: Request):
    configs = await llm_svc.list_configs()
    return templates.TemplateResponse(request, "settings.html", {
        "request": request,
        "llm_configs": configs,
    })


@router.get("/ops")
async def ops_page(request: Request):
    return templates.TemplateResponse(request, "ops.html", {
        "request": request,
    })
