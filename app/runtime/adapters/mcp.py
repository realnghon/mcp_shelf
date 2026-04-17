"""MCP adapter - loads tools from MCP servers via langchain-mcp-adapters."""

import inspect
from typing import Any

# MCP tool cache
_mcp_tool_cache: dict[str, list[Any]] = {}


async def get_mcp_tools(connection_config: dict[str, Any]) -> list[Any]:
    """Load tools from an MCP server using langchain-mcp-adapters.

    Supports:
    - HTTP transport
    - streamable_http transport
    """
    cache_key = connection_config.get("endpoint_url", "")
    if cache_key and cache_key in _mcp_tool_cache:
        return _mcp_tool_cache[cache_key]

    transport = _normalize_transport(connection_config.get("transport", "http"))
    endpoint_url = connection_config.get("endpoint_url", "")
    headers = connection_config.get("headers_template", {})

    if not endpoint_url:
        return []

    tools = []

    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient

        server_config = {
            "mcp-server": {
                "url": endpoint_url,
                "transport": transport,
            }
        }

        if headers:
            server_config["mcp-server"]["headers"] = headers

        client = MultiServerMCPClient(server_config)  # type: ignore[arg-type]
        try:
            mcp_tools = client.get_tools()
            if inspect.isawaitable(mcp_tools):
                mcp_tools = await mcp_tools
            tools = list(mcp_tools or [])
        finally:
            close_fn = getattr(client, "aclose", None)
            if callable(close_fn):
                close_result = close_fn()
                if inspect.isawaitable(close_result):
                    await close_result

    except ImportError:
        import logging
        logging.getLogger(__name__).warning(
            "langchain-mcp-adapters not installed. MCP tools unavailable."
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Failed to load MCP tools from {endpoint_url}: {e}")

    if cache_key and tools:
        _mcp_tool_cache[cache_key] = tools

    return tools


def clear_mcp_cache(endpoint_url: str | None = None):
    """Clear MCP tool cache."""
    if endpoint_url:
        _mcp_tool_cache.pop(endpoint_url, None)
    else:
        _mcp_tool_cache.clear()


def _normalize_transport(raw_transport: str) -> str:
    mapping = {
        "http": "streamable_http",
        "streamable_http": "streamable_http",
        "sse": "sse",
    }
    return mapping.get((raw_transport or "").lower(), raw_transport)
