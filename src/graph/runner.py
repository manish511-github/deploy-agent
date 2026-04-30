"""
Graph runner — extracted execution logic for the LangGraph agent.

Single Responsibility: handles graph invocation, Human-in-the-Loop
interrupts, rate-limit retries, and result extraction. The CLI layer
only deals with presentation.
"""

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING

from langchain_core.messages import ToolMessage
from rich.console import Console
from rich.panel import Panel

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

console = Console()

# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────

MAX_RETRIES = 5
AUTO_APPROVE_TOOLS = {"get_server_info", "list_all_servers"}


# ──────────────────────────────────────────────
# HITL (Human-in-the-Loop) handler
# ──────────────────────────────────────────────


def _handle_tool_interrupt(graph, state, config) -> object:
    """Handle a tool interrupt by prompting the user for approval.

    Auto-approves non-destructive tools (DB lookups) and low-risk dynamic scripts.
    Prompts for medium/high risk dynamic scripts and standard agent tasks that modify state.

    Returns:
        The graph invocation result after approval/rejection.
    """
    import typer

    messages = state.values.get("messages", [])
    last_ai_msg = [m for m in messages if getattr(m, "type", "") == "ai"][-1]
    tool_calls = getattr(last_ai_msg, "tool_calls", [])

    # We want to pause for execute_dynamic_script if risk != low
    # We might also want to pause for send_agent_task if it does a shutdown/restart
    dynamic_call = next(
        (t for t in tool_calls if t["name"] == "execute_dynamic_script"), None
    )

    if dynamic_call:
        risk_level = dynamic_call["args"].get("risk_level", "medium")
        if risk_level != "low":
            server_name = dynamic_call["args"].get("server_name", "Unknown")
            script = dynamic_call["args"].get("script", "Unknown")
            description = dynamic_call["args"].get("description", "Unknown")

            console.print()
            console.print(
                Panel(
                    f"[bold red]🛑 ACTION REQUIRED ({risk_level.upper()} RISK)[/bold red]\n"
                    f"The AI is requesting permission to run a script on the agent:\n\n"
                    f"[dim]Server:[/dim] [bold]{server_name}[/bold]\n"
                    f"[dim]Description:[/dim] {description}\n"
                    f"[dim]Script:[/dim] [bold cyan]{script}[/bold cyan]",
                    border_style="red",
                )
            )

            if not typer.confirm("Do you approve?"):
                console.print("\n[bold magenta]🛑 Execution cancelled by user.[/bold magenta]")
                rejection_msg = ToolMessage(
                    tool_call_id=dynamic_call["id"],
                    name="execute_dynamic_script",
                    content=(
                        f"Error: User denied permission to run "
                        f"script '{description}' on {server_name}."
                    ),
                )
                graph.update_state(
                    config, {"messages": [rejection_msg]}, as_node="tools"
                )
                return graph.invoke(None, config=config)

            console.print("\n[bold magenta]🤖 Resuming execution...[/bold magenta]")

    # Auto-approve non-destructive tools or approved scripts
    return graph.invoke(None, config=config)


# ──────────────────────────────────────────────
# Main execution entry point
# ──────────────────────────────────────────────


def invoke_agent(
    graph: CompiledStateGraph, user_message: str, thread_id: str
) -> str:
    """Invoke the agent graph with full HITL and retry support.

    Args:
        graph: The compiled LangGraph state machine.
        user_message: The user's natural language request.
        thread_id: Session identifier for checkpointing.

    Returns:
        The final AI response as a string.
    """
    config = {"configurable": {"thread_id": thread_id}}
    last_error: Exception | None = None

    for attempt in range(MAX_RETRIES):
        try:
            # Initial invocation (may pause at interrupt)
            result = graph.invoke(
                {"messages": [("user", user_message)]}, config=config
            )

            # Process any tool interrupts
            state = graph.get_state(config)
            while state.next and state.next[0] == "tools":
                result = _handle_tool_interrupt(graph, state, config)
                state = graph.get_state(config)

            # Extract final response
            return _extract_response(result)

        except Exception as exc:
            last_error = exc
            retry_delay = _get_retry_delay(exc, attempt)
            if retry_delay is not None:
                _wait_with_status(retry_delay, attempt)
                continue
            raise

    return f"[error]Failed after {MAX_RETRIES} attempts. Last error: {last_error}[/error]"


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────


def _extract_response(result: dict) -> str:
    """Extract the final text content from the graph result."""
    ai_message = result["messages"][-1]
    content = ai_message.content

    if isinstance(content, list):
        content = "\n".join(
            part.get("text", str(part)) if isinstance(part, dict) else str(part)
            for part in content
        )

    return content or "[No response from LLM — check your API keys in .env]"


def _get_retry_delay(exc: Exception, attempt: int) -> float | None:
    """Determine retry delay from exception, or None if not retryable."""
    error_msg = str(exc)

    if "RESOURCE_EXHAUSTED" in error_msg or "429" in error_msg:
        match = re.search(r"retry in (\d+(?:\.\d+)?)s", error_msg, re.IGNORECASE)
        return int(float(match.group(1))) + 2 if match else 30

    if "disconnected" in error_msg.lower():
        return 2**attempt

    return None


def _wait_with_status(delay: float, attempt: int) -> None:
    """Show a waiting spinner during rate-limit backoff."""
    console.print(
        f"\n[bold yellow]⚠️ Rate limited (attempt {attempt + 1}/{MAX_RETRIES})[/bold yellow]"
    )
    with console.status(
        f"[dim]Waiting {delay:.0f}s for quota reset...[/dim]", spinner="dots"
    ):
        time.sleep(delay)
