"""Local and capability-backed tools available to the runtime."""

from __future__ import annotations

import ast
import importlib
import inspect
import operator
from typing import Any

import httpx
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field


class EchoInput(BaseModel):
    message: str = Field(description="Message to echo back")


class CalculatorInput(BaseModel):
    expression: str = Field(description="Mathematical expression to evaluate")


class HttpFetchInput(BaseModel):
    url: str = Field(description="Absolute URL to fetch")


class PluginInput(BaseModel):
    input: str = Field(description="Free-form input for the plugin function")


async def _echo(message: str) -> str:
    return f"Echo: {message}"


async def _calculator(expression: str) -> str:
    """Safely evaluate a mathematical expression."""
    ops = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
    }

    def _eval(node: ast.AST) -> float | int:
        if isinstance(node, ast.Constant):
            if not isinstance(node.value, (int, float)):
                raise ValueError("Only numeric constants are allowed")
            return node.value
        if isinstance(node, ast.BinOp):
            if type(node.op) not in ops:
                raise ValueError(f"Unsupported operation: {type(node.op).__name__}")
            return ops[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp):
            if type(node.op) not in ops:
                raise ValueError(f"Unsupported operation: {type(node.op).__name__}")
            return ops[type(node.op)](_eval(node.operand))
        raise ValueError(f"Unsupported expression node: {type(node).__name__}")

    try:
        tree = ast.parse(expression, mode="eval")
        result = _eval(tree.body)
        return str(result)
    except Exception as exc:
        return f"Error: {exc}"


async def _http_fetch(url: str, timeout_s: float = 15.0) -> str:
    """Fetch a URL and return the response text."""
    try:
        timeout = max(float(timeout_s), 1.0)
    except (TypeError, ValueError):
        timeout = 15.0

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.text
    except Exception as exc:
        return f"Error fetching {url}: {exc}"


def get_local_tools() -> list[StructuredTool]:
    """Always-on local tools."""
    return [
        StructuredTool.from_function(
            coroutine=_echo,
            name="echo",
            description="Echo back the provided message. Useful for testing.",
            args_schema=EchoInput,
        ),
        StructuredTool.from_function(
            coroutine=_calculator,
            name="calculator",
            description="Evaluate a mathematical expression safely.",
            args_schema=CalculatorInput,
        ),
    ]


def get_local_tool_catalog() -> list[dict[str, Any]]:
    """Metadata for always-on local tools shown in the UI shelf."""
    return [
        {
            "id": "builtin-calculator",
            "kind": "tool",
            "name": "Calculator",
            "slug": "calculator",
            "description": "Evaluate a mathematical expression safely.",
            "status": "active",
            "is_builtin": True,
        },
    ]


def get_capability_tools(
    capability: dict[str, Any],
    config: dict[str, Any],
) -> list[StructuredTool]:
    """Resolve registry `tool` capabilities into executable LangChain tools."""
    slug = capability.get("slug", "")
    description = capability.get("description") or f"Capability tool: {slug}"
    transport = (config or {}).get("transport", "local")

    if slug == "calculator":
        return [
            StructuredTool.from_function(
                coroutine=_calculator,
                name="calculator",
                description=description,
                args_schema=CalculatorInput,
            )
        ]

    if slug == "http-fetch":
        timeout = (config or {}).get("timeout_s", 15)

        async def _fetch_tool(url: str) -> str:
            return await _http_fetch(url=url, timeout_s=timeout)

        return [
            StructuredTool.from_function(
                coroutine=_fetch_tool,
                name="http_fetch",
                description=description,
                args_schema=HttpFetchInput,
            )
        ]

    if transport == "plugin":
        plugin_tool = _build_plugin_tool(capability, config)
        return [plugin_tool] if plugin_tool else []

    return []


def _build_plugin_tool(
    capability: dict[str, Any],
    config: dict[str, Any],
) -> StructuredTool | None:
    """Load a local Python function as a plugin-backed tool.

    Expected config:
    {
      "transport": "plugin",
      "module": "pkg.module",
      "callable": "function_name",
      "tool_name": "optional_tool_name"
    }
    """
    module_name = config.get("module")
    callable_name = config.get("callable")
    if not module_name or not callable_name:
        return None

    module = importlib.import_module(module_name)
    func = getattr(module, callable_name)
    if not callable(func):
        return None

    async def _plugin_wrapper(input: str) -> str:
        result = func(input)
        if inspect.isawaitable(result):
            result = await result
        return str(result)

    tool_name = config.get("tool_name") or capability.get("slug") or "plugin_tool"
    description = capability.get("description") or f"Plugin tool from {module_name}.{callable_name}"

    return StructuredTool.from_function(
        coroutine=_plugin_wrapper,
        name=tool_name,
        description=description,
        args_schema=PluginInput,
    )
