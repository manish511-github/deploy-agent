"""
LangGraph State Schema

Defines the data structure that flows through every node in the graph.
Uses MessagesState as base to get built-in message history tracking.
"""

from __future__ import annotations

from typing import Annotated
from typing_extensions import TypedDict
from langgraph.graph import MessagesState


class ServerInfo(TypedDict, total=False):
    """Information about a target server."""
    server_id: str
    hostname: str
    ip_address: str
    os_name: str
    os_version: str
    status: str


class AgentState(MessagesState):
    """
    Main state flowing through the LangGraph state machine.
    
    Extends MessagesState which automatically tracks the conversation
    message history (HumanMessage, AIMessage, ToolMessage, etc.)
    
    Phase 1 fields:
        intent:         Classified user intent (status_check, execute, query)
        target_servers: Servers involved in this operation
        tool_results:   Accumulated results from tool executions
        error:          Error message if something failed
        retry_count:    Number of retries attempted
    """

    # What the user wants
    intent: str

    # Which servers are involved
    target_servers: list[ServerInfo]

    # Execution tracking
    tool_results: list[dict]

    # Error handling
    error: str | None
    retry_count: int
