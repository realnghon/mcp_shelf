from app.runtime.state import AgentState
from app.repositories.binding_repo import BindingRepo


async def load_binding_node(state: AgentState) -> dict:
    """Load binding config and attached capabilities."""
    binding_id = state.get("binding_id")
    selected_capabilities = []

    if binding_id:
        repo = BindingRepo()
        binding = await repo.get_by_id(binding_id)
        if binding:
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

    return {
        "selected_capabilities": selected_capabilities,
        "current_step": 0,
        "error": None,
    }
