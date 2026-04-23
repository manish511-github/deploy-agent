"""
Planner node — analyzes user requests and generates execution plans.

Single Responsibility: read the conversation, produce a structured plan.
Does NOT execute commands or interact with tools.
"""

from __future__ import annotations

from langchain_core.messages import SystemMessage
from pydantic import BaseModel, Field

from src.graph.state import AgentState
from src.graph.nodes.agent import get_llm_without_tools

PLANNER_SYSTEM_PROMPT = """\
You are the Operations Architect for DeployAI.
Your sole responsibility is to analyze the user's request (and any past errors)
and formulate a clear, chronological step-by-step execution plan.

You DO NOT execute commands yourself. You architect the strategy for the Executor agent.

Keep your steps concise and actionable. If the user asks you to check status,
your steps should be the diagnostic commands.

If the previous review_status was 'rejected', analyze the recent tool outputs
in the conversation history to understand what failed, and generate a new plan
to fix it.
"""


class DeploymentPlan(BaseModel):
    """Structured output schema for the Planner LLM."""

    plan: list[str] = Field(
        description=(
            "A sequential list of actionable steps or shell commands "
            "required to fulfill the user's request. Make sure steps "
            "are self-contained. E.g., ['apt-get update', 'apt-get install nginx -y']"
        )
    )


def planner_node(state: AgentState) -> dict:
    """Analyze the request and generate an execution plan.

    Returns:
        State update with the plan, reset step counter, and pending status.
    """
    llm = get_llm_without_tools()
    structured_llm = llm.with_structured_output(DeploymentPlan)

    messages = state.get("messages", [])
    prompt = [SystemMessage(content=PLANNER_SYSTEM_PROMPT)] + messages

    response = structured_llm.invoke(prompt)

    return {
        "plan": response.plan,
        "current_step": 0,
        "review_status": "pending",
    }
