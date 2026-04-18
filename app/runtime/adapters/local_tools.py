"""Local and capability-backed tools available to the runtime."""

from __future__ import annotations

import ast
import asyncio
import importlib
import inspect
import json
import operator
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Literal
from urllib.parse import unquote, urlparse

import httpx
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.core.config import settings
from app.runtime.adapters.builtin_catalog import load_builtin_capabilities


class EchoInput(BaseModel):
    message: str = Field(description="Message to echo back")


class CalculatorInput(BaseModel):
    expression: str = Field(description="Mathematical expression to evaluate")


class HttpFetchInput(BaseModel):
    url: str = Field(description="Absolute URL to fetch")
    timeout_s: float = Field(default=15.0, description="Timeout in seconds")


class PluginInput(BaseModel):
    input: str = Field(description="Free-form input for the plugin function")


class CodeRunInput(BaseModel):
    script: str = Field(description="Code script to execute")
    type: Literal["python", "powershell"] = Field(default="python", description="Script type")
    timeout: int = Field(default=60, description="Execution timeout in seconds")
    cwd: str | None = Field(default=None, description="Optional working directory")
    inline_eval: bool = Field(default=False, description="Reserved flag for compatibility")


class FileReadInput(BaseModel):
    path: str = Field(description="File path")
    start: int = Field(default=1, description="Start line number (1-based)")
    count: int = Field(default=200, description="Number of lines to read")
    keyword: str | None = Field(default=None, description="Optional keyword search")
    show_linenos: bool = Field(default=True, description="Whether to render line numbers")


class FileWriteInput(BaseModel):
    path: str = Field(description="File path")
    content: str = Field(description="File content to write")
    mode: Literal["overwrite", "append", "prepend"] = Field(default="overwrite")


class FilePatchInput(BaseModel):
    path: str = Field(description="File path")
    old_content: str = Field(description="Unique old text block to replace")
    new_content: str = Field(description="New text block")


class WebScanInput(BaseModel):
    tabs_only: bool = Field(default=False)
    switch_tab_id: str | None = Field(default=None)
    text_only: bool = Field(default=False)


class WebExecuteJsInput(BaseModel):
    script: str = Field(description="JavaScript string. In this server mode, include URL for navigation")
    save_to_file: str | None = Field(default=None)
    no_monitor: bool = Field(default=False)
    switch_tab_id: str | None = Field(default=None)


class AskUserInput(BaseModel):
    question: str = Field(description="Question to ask the user")
    candidates: list[str] = Field(default_factory=list, description="Optional quick candidates")


class UpdateWorkingCheckpointInput(BaseModel):
    key_info: str = Field(description="Working checkpoint text")
    related_sop: str | None = Field(default=None, description="Related SOP names")


class StartLongTermUpdateInput(BaseModel):
    pass


def _memory_dir() -> Path:
    path = settings.data_dir / "memory"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _working_checkpoint_file() -> Path:
    return _memory_dir() / "working_checkpoint.json"


def _long_term_memory_file() -> Path:
    return _memory_dir() / "long_term_memory.json"


def _web_tabs_file() -> Path:
    return _memory_dir() / "web_tabs.json"


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


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
    if url.startswith("file://"):
        try:
            parsed = urlparse(url)
            path_text = unquote(parsed.path or "")
            if sys.platform.startswith("win") and re.match(r"^/[a-zA-Z]:", path_text):
                path_text = path_text[1:]
            if not path_text and parsed.netloc:
                path_text = unquote(parsed.netloc)
            target = Path(path_text)
            return target.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            return f"Error fetching {url}: {exc}"

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


async def _code_run(
    script: str,
    type: Literal["python", "powershell"] = "python",
    timeout: int = 60,
    cwd: str | None = None,
    inline_eval: bool = False,
) -> str:
    if inline_eval:
        return json.dumps({"ok": False, "error": "inline_eval is not supported in this runtime"}, ensure_ascii=False)
    if not script.strip():
        return json.dumps({"ok": False, "error": "script is required"}, ensure_ascii=False)

    timeout_s = max(int(timeout or 60), 1)
    run_env = dict(os.environ)
    # Force child Python process to use UTF-8 I/O on Windows to avoid gbk emoji failures.
    run_env["PYTHONUTF8"] = "1"
    run_env["PYTHONIOENCODING"] = "utf-8"
    if type == "powershell":
        cmd = ["powershell", "-NoProfile", "-Command", script]
    else:
        cmd = [sys.executable, "-X", "utf8", "-c", script]

    def _build_payload(returncode: int, stdout: str, stderr: str, fallback: str | None = None) -> str:
        payload = {
            "ok": returncode == 0,
            "exit_code": returncode,
            "stdout": stdout,
            "stderr": stderr,
        }
        if fallback:
            payload["runner"] = fallback
        return json.dumps(payload, ensure_ascii=False)

    def _run_sync() -> str:
        completed = subprocess.run(
            cmd,
            cwd=cwd if cwd else None,
            env=run_env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
        )
        return _build_payload(
            returncode=completed.returncode,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
            fallback="sync-subprocess",
        )

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd if cwd else None,
            env=run_env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
        return _build_payload(
            returncode=proc.returncode if proc.returncode is not None else -1,
            stdout=stdout_b.decode("utf-8", errors="replace"),
            stderr=stderr_b.decode("utf-8", errors="replace"),
        )
    except NotImplementedError:
        # Windows SelectorEventLoop does not support asyncio subprocess.
        try:
            return await asyncio.to_thread(_run_sync)
        except subprocess.TimeoutExpired:
            return json.dumps({"ok": False, "error": f"timeout after {timeout_s}s", "runner": "sync-subprocess"}, ensure_ascii=False)
        except Exception as exc:
            return json.dumps(
                {
                    "ok": False,
                    "error": f"{type(exc).__name__}: {exc!s}" or type(exc).__name__,
                    "runner": "sync-subprocess",
                },
                ensure_ascii=False,
            )
    except asyncio.TimeoutError:
        return json.dumps({"ok": False, "error": f"timeout after {timeout_s}s"}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps(
            {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc!s}" or type(exc).__name__,
                "runner": "async-subprocess",
            },
            ensure_ascii=False,
        )


async def _file_read(
    path: str,
    start: int = 1,
    count: int = 200,
    keyword: str | None = None,
    show_linenos: bool = True,
) -> str:
    target = Path(path)
    if not target.exists():
        return f"Error: file not found: {target}"

    lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    if keyword:
        needle = keyword.lower()
        idx = next((i for i, line in enumerate(lines) if needle in line.lower()), -1)
        if idx >= 0:
            start_idx = max(0, idx - 8)
            end_idx = min(len(lines), idx + 12)
        else:
            return f"Keyword '{keyword}' not found in {target}"
    else:
        start_idx = max(int(start) - 1, 0)
        end_idx = min(start_idx + max(int(count), 1), len(lines))

    chunk = lines[start_idx:end_idx]
    if show_linenos:
        return "\n".join(f"{start_idx + i + 1}: {line}" for i, line in enumerate(chunk))
    return "\n".join(chunk)


async def _file_write(path: str, content: str, mode: Literal["overwrite", "append", "prepend"] = "overwrite") -> str:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if mode == "overwrite":
        target.write_text(content, encoding="utf-8")
    elif mode == "append":
        with target.open("a", encoding="utf-8") as f:
            f.write(content)
    elif mode == "prepend":
        current = target.read_text(encoding="utf-8") if target.exists() else ""
        target.write_text(content + current, encoding="utf-8")
    else:
        return f"Error: unsupported mode '{mode}'"
    return f"Wrote {len(content)} chars to {target} (mode={mode})"


async def _file_patch(path: str, old_content: str, new_content: str) -> str:
    target = Path(path)
    if not target.exists():
        return f"Error: file not found: {target}"
    text = target.read_text(encoding="utf-8")
    occurrences = text.count(old_content)
    if occurrences == 0:
        return "Error: old_content not found"
    if occurrences > 1:
        return "Error: old_content is not unique"
    patched = text.replace(old_content, new_content, 1)
    target.write_text(patched, encoding="utf-8")
    return f"Patched {target}"


def _load_web_state() -> dict[str, Any]:
    return _read_json(_web_tabs_file(), {"current_tab_id": "tab-1", "tabs": []})


def _save_web_state(state: dict[str, Any]) -> None:
    _write_json(_web_tabs_file(), state)


def _switch_tab(state: dict[str, Any], tab_id: str | None) -> None:
    if tab_id and any(tab.get("id") == tab_id for tab in state.get("tabs", [])):
        state["current_tab_id"] = tab_id


async def _web_scan(tabs_only: bool = False, switch_tab_id: str | None = None, text_only: bool = False) -> str:
    state = _load_web_state()
    _switch_tab(state, switch_tab_id)
    tabs = state.get("tabs", [])
    current_id = state.get("current_tab_id")

    payload: dict[str, Any] = {
        "current_tab_id": current_id,
        "tabs": [{"id": tab.get("id"), "url": tab.get("url"), "title": tab.get("title")} for tab in tabs],
    }
    if tabs_only:
        return json.dumps(payload, ensure_ascii=False)

    current = next((tab for tab in tabs if tab.get("id") == current_id), None)
    if current:
        content = str(current.get("content", ""))
        if text_only:
            content = re.sub(r"<[^>]+>", " ", content)
            content = re.sub(r"\s+", " ", content).strip()
        payload["content"] = content[:8000]
    else:
        payload["content"] = ""
    return json.dumps(payload, ensure_ascii=False)


def _upsert_tab(state: dict[str, Any], tab: dict[str, Any]) -> None:
    tabs = state.setdefault("tabs", [])
    for idx, existing in enumerate(tabs):
        if existing.get("id") == tab["id"]:
            tabs[idx] = tab
            return
    tabs.append(tab)


def _extract_url(script: str) -> str | None:
    match = re.search(r"(?:https?|file)://[^\s'\"`<>]+", script)
    return match.group(0) if match else None


async def _web_execute_js(
    script: str,
    save_to_file: str | None = None,
    no_monitor: bool = False,
    switch_tab_id: str | None = None,
) -> str:
    _ = no_monitor  # compatibility
    state = _load_web_state()
    _switch_tab(state, switch_tab_id)
    tab_id = state.get("current_tab_id") or "tab-1"
    url = _extract_url(script)

    if url:
        content = await _http_fetch(url, timeout_s=20)
        tab = {
            "id": tab_id,
            "url": url,
            "title": url,
            "content": content,
        }
        _upsert_tab(state, tab)
        _save_web_state(state)
        payload = {"ok": True, "tab_id": tab_id, "url": url, "content_len": len(content)}
    else:
        payload = {
            "ok": False,
            "message": "No URL detected in script. Include a URL for navigation in server mode.",
            "tab_id": tab_id,
        }

    result_text = json.dumps(payload, ensure_ascii=False)
    if save_to_file:
        Path(save_to_file).parent.mkdir(parents=True, exist_ok=True)
        Path(save_to_file).write_text(result_text, encoding="utf-8")
        return json.dumps({"ok": True, "saved_to_file": save_to_file}, ensure_ascii=False)
    return result_text


async def _ask_user(question: str, candidates: list[str] | None = None) -> str:
    choices = candidates or []
    return json.dumps({"ask_user": {"question": question, "candidates": choices}}, ensure_ascii=False)


async def _update_working_checkpoint(key_info: str, related_sop: str | None = None) -> str:
    payload = {
        "key_info": key_info,
        "related_sop": related_sop or "",
        "updated_at": _now(),
    }
    _write_json(_working_checkpoint_file(), payload)
    return json.dumps({"ok": True, "working_checkpoint": payload}, ensure_ascii=False)


async def _start_long_term_update() -> str:
    current = _read_json(_working_checkpoint_file(), {})
    if not isinstance(current, dict) or not current.get("key_info"):
        return json.dumps({"ok": False, "error": "working checkpoint is empty"}, ensure_ascii=False)

    archive = _read_json(_long_term_memory_file(), [])
    if not isinstance(archive, list):
        archive = []
    archive.append(
        {
            "key_info": current.get("key_info", ""),
            "related_sop": current.get("related_sop", ""),
            "source_updated_at": current.get("updated_at"),
            "archived_at": _now(),
        }
    )
    _write_json(_long_term_memory_file(), archive)
    return json.dumps({"ok": True, "entries": len(archive)}, ensure_ascii=False)


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


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
        StructuredTool.from_function(
            coroutine=_http_fetch,
            name="http_fetch",
            description="Fetch a URL and return response text.",
            args_schema=HttpFetchInput,
        ),
        StructuredTool.from_function(
            coroutine=_code_run,
            name="code_run",
            description="Execute python or powershell script.",
            args_schema=CodeRunInput,
        ),
        StructuredTool.from_function(
            coroutine=_file_read,
            name="file_read",
            description="Read file content with optional line range and keyword.",
            args_schema=FileReadInput,
        ),
        StructuredTool.from_function(
            coroutine=_file_write,
            name="file_write",
            description="Create/overwrite/append/prepend file content.",
            args_schema=FileWriteInput,
        ),
        StructuredTool.from_function(
            coroutine=_file_patch,
            name="file_patch",
            description="Patch unique old text block in a file.",
            args_schema=FilePatchInput,
        ),
        StructuredTool.from_function(
            coroutine=_web_scan,
            name="web_scan",
            description="Read current web tab snapshot and tab list.",
            args_schema=WebScanInput,
        ),
        StructuredTool.from_function(
            coroutine=_web_execute_js,
            name="web_execute_js",
            description="Execute web action; include URL in script for navigation in server mode.",
            args_schema=WebExecuteJsInput,
        ),
        StructuredTool.from_function(
            coroutine=_ask_user,
            name="ask_user",
            description="Request user decision in structured form.",
            args_schema=AskUserInput,
        ),
        StructuredTool.from_function(
            coroutine=_update_working_checkpoint,
            name="update_working_checkpoint",
            description="Update short-term working checkpoint persisted across sessions.",
            args_schema=UpdateWorkingCheckpointInput,
        ),
        StructuredTool.from_function(
            coroutine=_start_long_term_update,
            name="start_long_term_update",
            description="Archive current working checkpoint into long-term memory.",
            args_schema=StartLongTermUpdateInput,
        ),
    ]


def get_local_tool_catalog() -> list[dict[str, Any]]:
    """Metadata for always-on local tools shown in the UI shelf."""
    return load_builtin_capabilities()


def _local_tool_map() -> dict[str, StructuredTool]:
    tools = get_local_tools()
    return {tool.name: tool for tool in tools}


def get_capability_tools(
    capability: dict[str, Any],
    config: dict[str, Any],
) -> list[StructuredTool]:
    """Resolve registry `tool` capabilities into executable LangChain tools."""
    slug = capability.get("slug", "")
    transport = (config or {}).get("transport", "local")

    local_map = _local_tool_map()
    normalized = slug.replace("-", "_")
    if normalized in local_map:
        return [local_map[normalized]]

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
