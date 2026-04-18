from fastapi import APIRouter, HTTPException

from app.schemas.llm_config import LLMConfigCreate, LLMConfigUpdate
from app.services.llm_config_service import LLMConfigService

router = APIRouter()
svc = LLMConfigService()


@router.get("")
async def list_llm_configs():
    return await svc.list_configs()


@router.post("", status_code=201)
async def create_llm_config(data: LLMConfigCreate):
    return await svc.create_config(data)


@router.get("/{config_id}")
async def get_llm_config(config_id: str):
    config = await svc.get_config(config_id)
    if not config:
        raise HTTPException(404, "LLM config not found")
    return config


@router.put("/{config_id}")
async def update_llm_config(config_id: str, data: LLMConfigUpdate):
    config = await svc.update_config(config_id, data)
    if not config:
        raise HTTPException(404, "LLM config not found")
    return config


@router.delete("/{config_id}", status_code=204)
async def delete_llm_config(config_id: str):
    ok = await svc.delete_config(config_id)
    if not ok:
        raise HTTPException(404, "LLM config not found")


@router.post("/test")
async def test_llm_connection(data: dict):
    """Test an LLM configuration by making a simple API call."""
    provider = data.get("provider", "openai")
    api_key = data.get("api_key")
    base_url = _normalize_openai_compatible_base_url(
        provider=provider,
        base_url=data.get("base_url"),
    )

    if not api_key:
        # Try resolving from existing config
        api_key = await svc.resolve_api_key(provider)

    if not api_key:
        return {"ok": False, "detail": "No API key provided or configured"}

    try:
        import httpx
        if provider == "openai":
            url = (base_url or "https://api.openai.com/v1") + "/models"
            headers = {"Authorization": f"Bearer {api_key}"}
        elif provider == "anthropic":
            url = (base_url or "https://api.anthropic.com") + "/v1/models"
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            }
        else:
            url = base_url + "/models" if base_url else ""
            headers = {"Authorization": f"Bearer {api_key}"}

        if not url:
            return {"ok": False, "detail": "No endpoint to test"}

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=headers)

        return {"ok": resp.status_code < 400, "status_code": resp.status_code}
    except Exception as e:
        return {"ok": False, "detail": str(e)}


def _normalize_openai_compatible_base_url(provider: str, base_url: str | None) -> str | None:
    if not base_url:
        return base_url
    if provider not in {"openai", "custom"}:
        return base_url
    normalized = base_url.rstrip("/")
    if normalized.endswith("/v1"):
        return normalized
    return f"{normalized}/v1"
