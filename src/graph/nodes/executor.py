"""
Executor node — executes one step of the plan at a time.

Single Responsibility: take the current plan step, invoke the LLM with
tools to execute it, and advance the step counter.
"""

from __future__ import annotations

from langchain_core.messages import SystemMessage, ToolMessage

from src.graph.state import AgentState
from src.graph.nodes.agent import get_llm_with_tools

EXECUTOR_SYSTEM_PROMPT = """\
You are the System Administrator for DeployAI.
Your ONLY job is to execute the EXACT task provided below using the tools
available to you.
Do NOT attempt to execute other steps. Just run the tool commands necessary
to satisfy this specific task.

Current Task to Execute:
{task}
"""


def executor_node(state: AgentState) -> dict:
    """Execute the current step in the plan, or handle direct conversation.

    Two modes:
    1. Plan-driven (legacy): execute plan[current_step] via task-specific prompt.
    2. Plan-less (fast path): pass conversation directly to LLM with tools.

    Returns:
        State update with new messages and/or updated step counter.
    """
    plan = state.get("plan", [])
    current_step = state.get("current_step", 0)
    messages = state.get("messages", [])
    llm = get_llm_with_tools()

    # ── Plan-less fast path (planner disabled) ──────────────────────
    if not plan:
        # If last message is a ToolMessage, the tool just finished.
        # Invoke LLM again so it can process the result.
        response = llm.invoke(messages)
        return {"messages": [response]}

    # ── Plan-driven path (legacy) ───────────────────────────────────
    if current_step >= len(plan):
        return {}

    if messages and isinstance(messages[-1], ToolMessage):
        return {"current_step": current_step + 1}

    task = plan[current_step]
    sys_msg = SystemMessage(content=EXECUTOR_SYSTEM_PROMPT.format(task=task))
    response = llm.invoke([sys_msg] + messages)

    if not hasattr(response, "tool_calls") or not response.tool_calls:
        return {
            "messages": [response],
            "current_step": current_step + 1,
        }

    return {"messages": [response]}
