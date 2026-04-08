"""
DeployAI CLI — Beautiful terminal interface for the deployment agent.

Provides two modes:
1. Interactive chat: `deploy-ai chat` — conversational interface
2. One-shot run:     `deploy-ai run "check status of prod"` — single command
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.theme import Theme

from src.graph.graph import build_graph

# Rich console with custom theme
custom_theme = Theme(
    {
        "info": "cyan",
        "success": "bold green",
        "warning": "bold yellow",
        "error": "bold red",
        "agent": "bold magenta",
        "user": "bold blue",
    }
)
console = Console(theme=custom_theme)

# Typer app
app = typer.Typer(
    name="deploy-ai",
    help="🚀 AI-powered Linux server deployment management",
    rich_markup_mode="rich",
)


def _print_banner():
    """Print the welcome banner."""
    console.print(
        Panel(
            "[bold magenta]🚀 DeployAI[/bold magenta]\n"
            "[dim]AI-powered Linux Server Management[/dim]\n\n"
            "[dim]Type your request in natural language.[/dim]\n"
            "[dim]Type [bold]quit[/bold] or [bold]exit[/bold] to leave.[/dim]",
            border_style="magenta",
            padding=(1, 2),
        )
    )


from langgraph.types import Command

def _invoke_agent(graph, user_message: str, thread_id: str) -> str:
    """Invoke the agent graph and handle interactive Human-in-the-Loop."""
    import time
    import re
    config = {"configurable": {"thread_id": thread_id}}
    
    max_retries = 5
    last_error = None

    for attempt in range(max_retries):
        try:
            # 1. Initial invocation (can pause)
            result = graph.invoke({"messages": [("user", user_message)]}, config=config)
            
            # 2. Check for node interrupts using LangGraph's state API
            state = graph.get_state(config)
            while state.next and state.next[0] == "tools":
                # Find the pending tool calls in the state
                messages = state.values.get("messages", [])
                last_ai_msg = [m for m in messages if getattr(m, "type", "") == "ai"][-1]
                tool_calls = getattr(last_ai_msg, "tool_calls", [])
                
                # Check if it's trying to execute SSH
                ssh_call = next((t for t in tool_calls if t["name"] == "ssh_execute"), None)
                
                if ssh_call:
                    server_ip = ssh_call["args"].get("server_ip", "Unknown")
                    command = ssh_call["args"].get("command", "Unknown")
                    
                    console.print()
                    console.print(Panel(
                        f"[bold red]🛑 ACTION REQUIRED[/bold red]\n"
                        f"The AI is requesting permission to run a command via SSH:\n\n"
                        f"[dim]Server:[/dim] [bold]{server_ip}[/bold]\n"
                        f"[dim]Command:[/dim] [bold cyan]{command}[/bold cyan]",
                        border_style="red"
                    ))
                    
                    approval = typer.confirm(f"Do you approve?")
                    
                    if not approval:
                        # User rejected! We need to stop the tool from executing.
                        # We send a ToolMessage simulating the rejection so the LLM knows.
                        console.print("\n[agent]🛑 Execution cancelled by user.[/agent]")
                        from langchain_core.messages import ToolMessage
                        rejection_msg = ToolMessage(
                            tool_call_id=ssh_call["id"],
                            name="ssh_execute",
                            content=f"Error: User explicitly denied permission to run command '{command}' on {server_ip}."
                        )
                        # Push the fake error into state and invoke normally
                        graph.update_state(config, {"messages": [rejection_msg]}, as_node="tools")
                        result = graph.invoke(None, config=config)
                    else:
                        # User approved! Resume execution normally.
                        console.print("\n[agent]🤖 Resuming execution...[/agent]")
                        result = graph.invoke(None, config=config)
                else:
                    # It's a harmless tool (like get_server_info), auto-approve it
                    result = graph.invoke(None, config=config)
                
                # Update state iterator for the while loop
                state = graph.get_state(config)

            # 3. The graph successfully finished, extract final string
            ai_message = result["messages"][-1]
            content = ai_message.content

            # Handle edge cases: Gemini can return list-of-parts or empty on errors
            if isinstance(content, list):
                # Extract text from content parts
                content = "\n".join(
                    part.get("text", str(part)) if isinstance(part, dict) else str(part)
                    for part in content
                )
            if not content:
                content = "[No response from LLM — check your GEMINI_API_KEY in .env]"

            return content

        except Exception as e:
            last_error = e
            error_msg = str(e)
            
            # Handle rate limiting — extract retry delay from API response
            if "RESOURCE_EXHAUSTED" in error_msg or "429" in error_msg:
                # Try to extract retry delay from error message
                delay_match = re.search(r'retry in (\d+(?:\.\d+)?)s', error_msg, re.IGNORECASE)
                wait = int(float(delay_match.group(1))) + 2 if delay_match else 30
                console.print(f"\n[warning]⚠️ Rate limited (attempt {attempt+1}/{max_retries})[/warning]")
                with console.status(f"[dim]Waiting {wait}s for quota reset...[/dim]", spinner="dots"):
                    time.sleep(wait)
                continue
            # Handle server disconnects
            elif "disconnected" in error_msg.lower():
                wait = 2 ** attempt
                console.print(f"\n[warning]⚠️ API disconnected (attempt {attempt+1}/{max_retries})[/warning]")
                console.print(f"[dim]Retrying in {wait}s...[/dim]")
                time.sleep(wait)
                continue
            else:
                raise

    return f"[error]Failed after {max_retries} attempts. Last error: {last_error}[/error]"


@app.command()
def chat():
    """
    🗣️  Start an interactive chat session with DeployAI.

    Have a conversation about your servers — check status, run commands,
    deploy services, and more.
    """
    _print_banner()

    console.print("\n[info]Building agent graph...[/info]")
    graph = build_graph()
    console.print("[success]✓ Agent ready![/success]\n")

    while True:
        try:
            user_input = console.input("[bold blue]You >[/bold blue] ").strip()

            if not user_input:
                continue

            if user_input.lower() in ("quit", "exit", "q", "bye"):
                console.print("\n[dim]👋 Goodbye![/dim]")
                raise typer.Exit()

            # Show thinking indicator
            with console.status("[agent]🤖 Thinking...[/agent]", spinner="dots"):
                response = _invoke_agent(graph, user_input, thread_id="chat_session")

            # Display response as markdown for nice formatting
            console.print()
            console.print(Panel(Markdown(response), border_style="magenta", title="🤖 DeployAI"))
            console.print()

        except KeyboardInterrupt:
            console.print("\n[dim]👋 Goodbye![/dim]")
            raise typer.Exit()
        except Exception as e:
            console.print(f"\n[error]Error: {e}[/error]\n")


@app.command()
def run(
    message: str = typer.Argument(help="The request to send to the AI agent"),
):
    """
    ⚡ Send a single request to DeployAI and get a response.

    Example:
        deploy-ai run "check the status of prod-server"
        deploy-ai run "list all my servers"
        deploy-ai run "show docker containers on staging"
    """
    console.print("[info]Building agent graph...[/info]")
    graph = build_graph()

    with console.status("[agent]🤖 Working...[/agent]", spinner="dots"):
        response = _invoke_agent(graph, message, thread_id="run_session")

    console.print()
    console.print(Panel(Markdown(response), border_style="magenta", title="🤖 DeployAI"))


@app.command()
def status():
    """📊 Check if DeployAI is configured correctly."""
    from src.config import settings

    console.print(Panel("[bold]DeployAI Configuration Status[/bold]", border_style="cyan"))

    # Check OpenAI key
    if settings.openai_api_key and settings.openai_api_key != "sk-your-key-here":
        console.print("  [success]✓[/success] OpenAI API key configured")
    else:
        console.print("  [error]✗[/error] OpenAI API key not set (check .env)")

    # Check database
    try:
        import psycopg2
        conn = psycopg2.connect(settings.database_url)
        conn.close()
        console.print("  [success]✓[/success] Database connection OK")
    except Exception as e:
        console.print(f"  [error]✗[/error] Database connection failed: {e}")

    # Check SSH key
    import os
    key_path = os.path.expanduser(settings.ssh_key_path)
    if os.path.exists(key_path):
        console.print(f"  [success]✓[/success] SSH key found at {key_path}")
    else:
        console.print(f"  [warning]⚠[/warning] SSH key not found at {key_path}")

    console.print(f"\n  [dim]Model: {settings.llm_model}[/dim]")
    console.print(f"  [dim]DB: {settings.database_url.split('@')[1] if '@' in settings.database_url else 'N/A'}[/dim]")


if __name__ == "__main__":
    app()
