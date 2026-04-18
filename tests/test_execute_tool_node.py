from app.runtime.nodes.execute_tool import execute_tool_node


class _DummyTool:
    name = "file_write"

    @staticmethod
    async def coroutine(path: str, content: str, mode: str = "overwrite") -> str:  # noqa: ARG004
        return f"Wrote {len(content)} chars to {path}"


async def test_execute_tool_node_does_not_hard_fail_on_bad_tool_args():
    state = {
        "messages": [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "tc_bad", "name": "file_write", "args": {}},
                ],
            }
        ],
        "available_tools": [_DummyTool()],
    }

    result = await execute_tool_node(state)
    assert result["error"] is None
    assert len(result["messages"]) == 2
    tool_msg = result["messages"][-1]
    assert tool_msg["role"] == "tool"
    assert "missing 2 required positional arguments" in (tool_msg.get("tool_result") or "")
