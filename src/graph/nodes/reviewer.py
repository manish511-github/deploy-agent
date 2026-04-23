"""
Reviewer node — evaluates execution results and decides next action.

Single Responsibility: read tool outputs, determine if the deployment
succeeded or failed, and provide user-facing feedback.
"""

from __future__ import annotations

from typing import Literal

from langchain_core.messages import AIMessage, SystemMessage
from pydantic import BaseModel, Field

from src.graph.state import AgentState
from src.graph.nodes.agent import get_llm_without_tools

REVIEWER_SYSTEM_PROMPT = """\
You are the Senior DevOps Reviewer for DeployAI.
Look at the conversation history and evaluate the outputs returned by the
Executor's tools against the user's overarching goal.

If the commands executed successfully and the expected state was achieved,
approve it.

CRITICAL: For your `feedback`, you MUST generate a thorough, user-facing
conversational response that includes the actual data retrieved by the tools
(like a list of servers or server stats). Do NOT just say 'Approved'.
The user needs to see the actual content!

If there were errors (e.g., 'command not found', 'Permission denied', or
service failed to start), reject it and provide detailed error feedback
so the Planner can rewrite a new strategy.
"""


class ReviewResult(BaseModel):
    """Structured output schema for the Reviewer LLM."""

    review_status: Literal["approved", "rejected"] = Field(
        description=(
            "Return 'approved' if the entire execution plan succeeded. "
            "Return 'rejected' if there was a failure requiring a new plan."
        )
    )
    feedback: str = Field(
        description=(
            "A user-friendly summary of the deployment success, or "
            "critical feedback/error logs explaining why it failed."
        )
    )


def reviewer_node(state: AgentState) -> dict:
    """Evaluate execution results and create a routing decision.

    Returns:
        State update with review_status and a feedback message.
    """
    llm = get_llm_without_tools()
    structured_llm = llm.with_structured_output(ReviewResult)

    messages = state.get("messages", [])
    prompt = [SystemMessage(content=REVIEWER_SYSTEM_PROMPT)] + messages

    response = structured_llm.invoke(prompt)

    return {
        "review_status": response.review_status,
        "messages": [AIMessage(content=response.feedback)],
    }
