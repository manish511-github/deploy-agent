"""
Graph builder — compiles the multi-agent LangGraph state machine.

Architecture:
  START → Planner → Executor ⇄ Tools → Reviewer → END
                                          ↓ (rejected)
                                       Planner (retry)
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver

from src.graph.state import AgentState
from src.tools import ALL_TOOLS
from src.graph.nodes.planner import planner_node
from src.graph.nodes.executor import executor_node
from src.graph.nodes.reviewer import reviewer_node


# ──────────────────────────────────────────────
# Routing functions
# ──────────────────────────────────────────────


def _route_after_executor(state: AgentState) -> str:
    """Determine where to go after the executor finishes a cycle.

    Returns:
        "tools"    — Executor generated a tool call; execute it.
        "executor" — More plan steps remain; loop back.
        "reviewer" — All steps exhausted; validate results.
    """
    messages = state.get("messages", [])

    # Did the executor request a tool call?
    if (
        messages
        and hasattr(messages[-1], "tool_calls")
        and messages[-1].tool_calls
    ):
        return "tools"

    # Are there remaining steps?
    current_step = state.get("current_step", 0)
    plan = state.get("plan", [])

    if current_step < len(plan):
        return "executor"

    return "reviewer"


def _route_after_reviewer(state: AgentState) -> str:
    """Determine if the deployment succeeded or needs a retry.

    Returns:
        END       — Reviewer approved; we're done.
        "planner" — Reviewer rejected; re-plan from errors.
    """
    if state.get("review_status") == "approved":
        return END
    return "planner"


# ──────────────────────────────────────────────
# Graph compilation
# ──────────────────────────────────────────────


def build_graph():
    """Build and compile the multi-agent LangGraph state machine.

    Returns:
        A compiled LangGraph with checkpointing and HITL interrupts.
    """
    workflow = StateGraph(AgentState)

    # ── Register nodes ───────────────────────
    workflow.add_node("planner", planner_node)
    workflow.add_node("executor", executor_node)
    workflow.add_node("reviewer", reviewer_node)
    workflow.add_node("tools", ToolNode(ALL_TOOLS))

    # ── Define edges ─────────────────────────
    # 1. Entry: START → Planner → Executor
    workflow.add_edge(START, "planner")
    workflow.add_edge("planner", "executor")

    # 2. Execution loop: Executor ⇄ Tools
    workflow.add_conditional_edges(
        "executor",
        _route_after_executor,
        {
            "tools": "tools",
            "executor": "executor",
            "reviewer": "reviewer",
        },
    )
    workflow.add_edge("tools", "executor")

    # 3. Validation: Reviewer → END or retry
    workflow.add_conditional_edges(
        "reviewer",
        _route_after_reviewer,
        {
            END: END,
            "planner": "planner",
        },
    )

    # ── Compile ──────────────────────────────
    return workflow.compile(
        checkpointer=MemorySaver(),
        interrupt_before=["tools"],  # HITL: pause before destructive ops
    )
