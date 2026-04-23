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
    """Execute the current step in the plan.

    Handles three scenarios:
    1. Plan exhausted → returns empty (no-op).
    2. Last message is a ToolMessage → the tool finished; advance step.
    3. Otherwise → invoke the LLM to generate a tool call.

    Returns:
        State update with new messages and/or updated step counter.
    """
    plan = state.get("plan", [])
    current_step = state.get("current_step", 0)
    messages = state.get("messages", [])

    # Plan exhausted — nothing to do
    if current_step >= len(plan):
        return {}

    # Tool just finished → advance to next step
    if messages and isinstance(messages[-1], ToolMessage):
        return {"current_step": current_step + 1}

    # Invoke LLM to execute the current step
    task = plan[current_step]
    llm = get_llm_with_tools()

    sys_msg = SystemMessage(content=EXECUTOR_SYSTEM_PROMPT.format(task=task))
    response = llm.invoke([sys_msg] + messages)

    # If the LLM answered directly (no tool call), count step as done
    if not hasattr(response, "tool_calls") or not response.tool_calls:
        return {
            "messages": [response],
            "current_step": current_step + 1,
        }

    # Tool call → let LangGraph's ToolNode handle execution
    return {"messages": [response]}
