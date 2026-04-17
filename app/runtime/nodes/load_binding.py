from app.runtime.assembly.preset_assembler import assemble_messages
from app.runtime.assembly.source_loader import load_sources
from app.runtime.state import AgentState


async def load_binding_node(state: AgentState) -> dict:
    """Load phase2 source layer and assemble binding-level preset."""
    loaded = await load_sources(state)
    binding = loaded.get("binding") or {}
    loaded["messages"] = assemble_messages(
        messages=loaded.get("messages", []),
        binding_system_prompt=binding.get("system_prompt") if isinstance(binding, dict) else None,
    )
    return loaded
