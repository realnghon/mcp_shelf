from app.repositories.binding_repo import BindingRepo
from app.runtime.state import AgentState


async def load_binding_node(state: AgentState) -> dict:
    """Load binding config and attached capabilities."""
    binding_id = state.get("binding_id")
    selected_capabilities = []
    max_steps = state.get("max_steps", 8)
    messages = list(state.get("messages", []))

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
                    "connection_config": {},  # will be filled from capability
                }
                for c in caps
                if c["is_enabled"]
            ]
            # Inject system prompt once at the start when missing.
            if binding.get("system_prompt"):
                has_system = any(m.get("role") == "system" for m in messages)
                if not has_system:
                    messages.insert(0, {"role": "system", "content": binding["system_prompt"]})

    return {
        "messages": messages,
        "selected_capabilities": selected_capabilities,
        "max_steps": max_steps,
        "current_step": 0,
        "error": None,
    }
