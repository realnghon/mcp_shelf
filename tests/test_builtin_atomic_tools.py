import json
from pathlib import Path
import asyncio

from app.runtime.adapters.local_tools import get_local_tools


def test_builtin_local_tools_include_atomic_and_memory_tools():
    names = {tool.name for tool in get_local_tools()}
    expected = {
        "code_run",
        "file_read",
        "file_write",
        "file_patch",
        "web_scan",
        "web_execute_js",
        "ask_user",
        "calculator",
        "http_fetch",
        "update_working_checkpoint",
        "start_long_term_update",
    }
    assert expected <= names


async def test_memory_tools_persist_across_calls(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    tools = {tool.name: tool for tool in get_local_tools()}

    update_tool = tools["update_working_checkpoint"]
    long_term_tool = tools["start_long_term_update"]
    assert update_tool.coroutine is not None
    assert long_term_tool.coroutine is not None

    await update_tool.coroutine(
        key_info="User prefers concise answers; deploy in Shanghai env",
        related_sop="memory_management_sop.md",
    )
    await long_term_tool.coroutine()

    memory_file = Path("data/memory/long_term_memory.json")
    assert memory_file.exists()
    payload = json.loads(memory_file.read_text(encoding="utf-8"))
    assert isinstance(payload, list)
    assert any("Shanghai" in (item.get("key_info") or "") for item in payload)


async def test_code_run_falls_back_when_async_subprocess_unavailable(monkeypatch):
    async def _raise_not_implemented(*args, **kwargs):  # noqa: ANN002, ANN003
        raise NotImplementedError()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _raise_not_implemented)
    tools = {tool.name: tool for tool in get_local_tools()}
    code_run = tools["code_run"]
    assert code_run.coroutine is not None

    result = await code_run.coroutine(script="print(1+2)", type="python", timeout=8)
    payload = json.loads(result)
    assert payload["ok"] is True
    assert payload.get("runner") == "sync-subprocess"
    assert "3" in (payload.get("stdout") or "")


async def test_code_run_handles_unicode_output():
    tools = {tool.name: tool for tool in get_local_tools()}
    code_run = tools["code_run"]
    assert code_run.coroutine is not None

    result = await code_run.coroutine(script="print('🧪 unicode ok')", type="python", timeout=8)
    payload = json.loads(result)
    assert payload["ok"] is True
    assert "unicode ok" in (payload.get("stdout") or "")
