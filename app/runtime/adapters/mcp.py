"""MCP adapter - loads tools from MCP servers via langchain-mcp-adapters."""

import json
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
    transport = _normalize_transport(connection_config.get("transport", "http"))
    cache_key = _build_cache_key(connection_config, transport)
    if cache_key and cache_key in _mcp_tool_cache:
        return _mcp_tool_cache[cache_key]

    server_cfg = _build_server_config(connection_config, transport)
    if not server_cfg:
        return []

    endpoint_url = str(connection_config.get("endpoint_url", ""))
    command = str(connection_config.get("command", ""))

    tools = []

    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient

        server_config = {"mcp-server": server_cfg}

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
        target = endpoint_url or command or "<unknown>"
        logging.getLogger(__name__).warning(f"Failed to load MCP tools from {target}: {e}")

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
        "streamablehttp": "streamable_http",
        "sse": "sse",
        "stdio": "stdio",
    }
    return mapping.get((raw_transport or "").lower(), raw_transport)


def _build_server_config(connection_config: dict[str, Any], transport: str) -> dict[str, Any] | None:
    if transport == "stdio":
        command = str(connection_config.get("command", "")).strip()
        if not command:
            return None

        cfg: dict[str, Any] = {
            "transport": "stdio",
            "command": command,
        }
        args = connection_config.get("args", [])
        if isinstance(args, list) and args:
            cfg["args"] = [str(v) for v in args]
        env = connection_config.get("env", {})
        if isinstance(env, dict) and env:
            cfg["env"] = {str(k): str(v) for k, v in env.items()}
        cwd = str(connection_config.get("cwd", "")).strip()
        if cwd:
            cfg["cwd"] = cwd
        return cfg

    endpoint_url = str(connection_config.get("endpoint_url", "")).strip()
    if not endpoint_url:
        return None
    cfg = {
        "transport": transport or "streamable_http",
        "url": endpoint_url,
    }
    headers = connection_config.get("headers_template", {})
    if isinstance(headers, dict) and headers:
        cfg["headers"] = headers
    return cfg


def _build_cache_key(connection_config: dict[str, Any], transport: str) -> str:
    if transport == "stdio":
        command = str(connection_config.get("command", "")).strip()
        args = connection_config.get("args", [])
        env = connection_config.get("env", {})
        return f"stdio:{command}:{json.dumps(args, sort_keys=True)}:{json.dumps(env, sort_keys=True)}"
    endpoint_url = str(connection_config.get("endpoint_url", "")).strip()
    headers = connection_config.get("headers_template", {})
    return f"{transport}:{endpoint_url}:{json.dumps(headers, sort_keys=True)}"
