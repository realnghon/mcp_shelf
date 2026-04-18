import json
from pathlib import Path

from app.runtime.adapters.local_tools import get_local_tools


def test_code_run_utf8_guardrails_present():
    source = Path("app/runtime/adapters/local_tools.py").read_text(encoding="utf-8")
    assert "PYTHONUTF8" in source
    assert "PYTHONIOENCODING" in source
    assert '"-X", "utf8"' in source


async def test_http_fetch_supports_file_uri_with_unicode_and_spaces(tmp_path):
    tools = {tool.name: tool for tool in get_local_tools()}
    http_fetch = tools["http_fetch"]
    assert http_fetch.coroutine is not None

    target = tmp_path / "测试 folder" / "hello world.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    expected = "platform-uri-ok"
    target.write_text(expected, encoding="utf-8")

    result = await http_fetch.coroutine(url=target.resolve().as_uri(), timeout_s=5)
    assert expected in result


async def test_code_run_unicode_output_does_not_fail():
    tools = {tool.name: tool for tool in get_local_tools()}
    code_run = tools["code_run"]
    assert code_run.coroutine is not None

    result = await code_run.coroutine(
        script="print('🧪 cross-platform utf8')",
        type="python",
        timeout=8,
    )
    payload = json.loads(result)
    assert payload["ok"] is True
    assert "utf8" in (payload.get("stdout") or "")
