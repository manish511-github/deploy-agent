"""
Graph builder — compiles the LangGraph state machine.

Simplified architecture (planner + reviewer disabled for speed):
  START → Executor ⇄ Tools → END
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver

from src.graph.state import AgentState
from src.tools import ALL_TOOLS
from src.graph.nodes.executor import executor_node


# ──────────────────────────────────────────────
# Routing functions
# ──────────────────────────────────────────────


def _route_after_executor(state: AgentState) -> str:
    """Route after executor: tools if tool_calls present, else END."""
    messages = state.get("messages", [])
    if (
        messages
        and hasattr(messages[-1], "tool_calls")
        and messages[-1].tool_calls
    ):
        return "tools"
    return END


# ──────────────────────────────────────────────
# Graph compilation
# ──────────────────────────────────────────────


def build_graph(tools=None, checkpointer=None):
    """Build and compile the LangGraph state machine.

    Args:
        tools: Optional list of tools (defaults to ALL_TOOLS).
               Engine passes PermissionToolWrapper instances here.
        checkpointer: Optional checkpointer (defaults to MemorySaver).

    Returns:
        A compiled LangGraph.
    """
    from src.tools import ALL_TOOLS

    tool_list = tools if tools is not None else ALL_TOOLS
    cp = checkpointer if checkpointer is not None else MemorySaver()

    workflow = StateGraph(AgentState)

    # ── Register nodes ───────────────────────
    workflow.add_node("executor", executor_node)
    workflow.add_node("tools", ToolNode(tool_list))

    # ── Define edges ─────────────────────────
    workflow.add_edge(START, "executor")

    workflow.add_conditional_edges(
        "executor",
        _route_after_executor,
        {"tools": "tools", END: END},
    )
    workflow.add_edge("tools", "executor")

    return workflow.compile(checkpointer=cp)
