from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph

from app.runtime.state import AgentState
from app.runtime.nodes.load_binding import load_binding_node
from app.runtime.nodes.build_tools import build_tools_node
from app.runtime.nodes.call_model import call_model_node
from app.runtime.nodes.execute_tool import execute_tool_node
from app.runtime.nodes.finalize import finalize_node
from app.runtime.nodes.fail import fail_node


def should_continue(state: AgentState) -> str:
    """Decide next node after call_model."""
    messages = state.get("messages", [])
    if state.get("error"):
        return "fail"
    if state["current_step"] >= state["max_steps"]:
        return "fail"
    if not messages:
        return "finalize"

    last_msg = messages[-1]

    # If last message has tool_calls, execute tools
    if isinstance(last_msg, dict) and last_msg.get("tool_calls"):
        return "execute_tool"

    # If last message is from assistant without tool calls, we're done
    if isinstance(last_msg, dict) and last_msg.get("role") == "assistant":
        if last_msg.get("content"):
            return "finalize"

    return "finalize"


def should_retry(state: AgentState) -> str:
    """Decide next node after execute_tool."""
    if state.get("error"):
        return "fail"
    return "call_model"


def build_graph() -> CompiledStateGraph:
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("load_binding", load_binding_node)
    graph.add_node("build_tools", build_tools_node)
    graph.add_node("call_model", call_model_node)
    graph.add_node("execute_tool", execute_tool_node)
    graph.add_node("finalize", finalize_node)
    graph.add_node("fail", fail_node)

    # Set entry point
    graph.set_entry_point("load_binding")

    # Linear edges
    graph.add_edge("load_binding", "build_tools")
    graph.add_edge("build_tools", "call_model")

    # Conditional: after call_model
    graph.add_conditional_edges(
        "call_model",
        should_continue,
        {
            "execute_tool": "execute_tool",
            "finalize": "finalize",
            "fail": "fail",
        },
    )

    # Conditional: after execute_tool
    graph.add_conditional_edges(
        "execute_tool",
        should_retry,
        {
            "call_model": "call_model",
            "fail": "fail",
        },
    )

    # Terminal edges
    graph.add_edge("finalize", END)
    graph.add_edge("fail", END)

    return graph.compile()
