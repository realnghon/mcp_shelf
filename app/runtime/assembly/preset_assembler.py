from __future__ import annotations

from typing import Any


def assemble_messages(
    messages: list[dict[str, Any]],
    binding_system_prompt: str | None = None,
    prompt_fragments: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Assemble final system preset prompt from binding + prompt capabilities."""
    merged = [dict(msg) for msg in messages]

    chunks: list[str] = []
    if isinstance(binding_system_prompt, str) and binding_system_prompt.strip():
        chunks.append(binding_system_prompt.strip())

    if prompt_fragments:
        compact = [frag.strip() for frag in prompt_fragments if isinstance(frag, str) and frag.strip()]
        if compact:
            guidance = "Capability guidance:\n" + "\n".join(f"- {frag}" for frag in compact)
            chunks.append(guidance)

    if not chunks:
        return merged

    final_prompt = "\n\n".join(chunks)

    for msg in merged:
        if msg.get("role") == "system":
            current = msg.get("content")
            if isinstance(current, str) and final_prompt not in current:
                msg["content"] = f"{current}\n\n{final_prompt}".strip()
            return merged

    merged.insert(0, {"role": "system", "content": final_prompt})
    return merged

