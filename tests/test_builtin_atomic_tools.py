import json
from pathlib import Path

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
