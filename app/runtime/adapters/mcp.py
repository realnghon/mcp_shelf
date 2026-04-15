"""MCP adapter - loads tools from MCP servers via langchain-mcp-adapters."""

from typing import Any

from langchain_core.tools import StructuredTool

# MCP tool cache
_mcp_tool_cache: dict[str, list[StructuredTool]] = {}


async def get_mcp_tools(connection_config: dict[str, Any]) -> list[StructuredTool]:
    """Load tools from an MCP server using langchain-mcp-adapters.

    Supports:
    - HTTP transport
    - streamable_http transport
    """
    cache_key = connection_config.get("endpoint_url", "")
    if cache_key and cache_key in _mcp_tool_cache:
        return _mcp_tool_cache[cache_key]

    transport = connection_config.get("transport", "http")
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

        async with MultiServerMCPClient(server_config) as client:
            mcp_tools = client.get_tools()
            tools = list(mcp_tools)

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
