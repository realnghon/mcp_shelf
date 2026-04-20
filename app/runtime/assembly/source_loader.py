from __future__ import annotations

from typing import Any

from app.repositories.binding_repo import BindingRepo
from app.runtime.state import AgentState


async def load_sources(state: AgentState) -> dict[str, Any]:
    """Load binding-level sources and initial capability references."""
    binding_id = state.get("binding_id")
    selected_capabilities: list[dict[str, Any]] = []
    ad_hoc_capabilities: list[dict[str, Any]] = list(state.get("ad_hoc_capabilities", []))
    max_steps = int(state.get("max_steps", 8))
    messages = list(state.get("messages", []))
    binding: dict[str, Any] | None = None

    if binding_id:
        repo = BindingRepo()
        binding = await repo.get_by_id(binding_id)
        if binding:
            if binding.get("max_steps"):
                max_steps = int(binding["max_steps"])
            caps = await repo.list_capabilities(binding_id)
            selected_capabilities = [
                {
                    "capability_id": c["capability_id"],
                    "kind": c["capability_kind"],
                    "slug": c["capability_slug"],
                    "is_enabled": c["is_enabled"],
                    "runtime_overrides": c["runtime_overrides"],
                }
                for c in caps
                if c["is_enabled"]
            ]

    if ad_hoc_capabilities:
        merged: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in [*selected_capabilities, *ad_hoc_capabilities]:
            cap_id = str(item.get("capability_id") or "").strip()
            if not cap_id or cap_id in seen:
                continue
            seen.add(cap_id)
            merged.append(item)
        selected_capabilities = merged

    return {
        "binding": binding,
        "messages": messages,
        "selected_capabilities": selected_capabilities,
        "max_steps": max_steps,
        "current_step": 0,
        "error": None,
    }
