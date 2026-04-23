"""
LangGraph State Schema.

Defines the typed data structure that flows through every node in the
graph. Uses MessagesState as base for built-in message history tracking.
"""

from __future__ import annotations

from typing import Literal
from typing_extensions import TypedDict

from langgraph.graph import MessagesState


class ServerInfo(TypedDict, total=False):
    """Typed dictionary for target server metadata."""

    server_id: str
    hostname: str
    ip_address: str
    os_name: str
    os_version: str
    status: str


class AgentState(MessagesState):
    """Main state flowing through the LangGraph state machine.

    Extends MessagesState which automatically tracks the conversation
    message history (HumanMessage, AIMessage, ToolMessage, etc.)

    Attributes:
        intent: Classified user intent (status_check, execute, query).
        target_servers: Servers involved in this operation.
        tool_results: Accumulated results from tool executions.
        error: Error message if something failed.
        retry_count: Number of retries attempted.
        plan: Sequential steps from the Planner node.
        current_step: Index of the step currently being executed.
        review_status: Reviewer's verdict on the execution.
    """

    # ── User intent ──────────────────────────
    intent: str
    target_servers: list[ServerInfo]

    # ── Execution tracking ───────────────────
    tool_results: list[dict]
    error: str | None
    retry_count: int

    # ── Multi-agent pipeline ─────────────────
    plan: list[str]
    current_step: int
    review_status: Literal["pending", "approved", "rejected"]
