"""
DeployAI CLI — presentation layer for the deployment agent.

Single Responsibility: this module ONLY handles terminal UI (Rich),
user input (Typer), and delegates all execution to the graph runner.
"""

from __future__ import annotations

import asyncio
from uuid import UUID

import httpx
import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.theme import Theme

from src.cli.stream import StreamConsumer
from src.core.config import get_settings

# ──────────────────────────────────────────────
# Console configuration
# ──────────────────────────────────────────────

_theme = Theme(
    {
        "info": "cyan",
        "success": "bold green",
        "warning": "bold yellow",
        "error": "bold red",
        "agent": "bold magenta",
        "user": "bold blue",
    }
)
console = Console(theme=_theme)

# ──────────────────────────────────────────────
# Typer CLI app
# ──────────────────────────────────────────────

app = typer.Typer(
    name="deploy-ai",
    help="🚀 AI-powered Linux server deployment management",
    rich_markup_mode="rich",
)


def _print_banner() -> None:
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


def _get_base_url() -> str:
    """Resolve the server base URL from config.

    In Docker the server is at ``SERVER_BASE_URL`` (usually ``http://server:8000``).
    Outside Docker it defaults to ``http://localhost:8000``.
    """
    import os

    return os.environ.get("SERVER_BASE_URL", "http://localhost:8000")


# ──────────────────────────────────────────────
# Commands
# ──────────────────────────────────────────────


@app.command()
def chat(
    direct: bool = typer.Option(False, "--direct", help="Run graph directly without the HTTP server"),
) -> None:
    """🗣️  Start an interactive chat session with DeployAI."""
    if direct:
        _chat_direct()
        return

    _chat_server()


def _chat_server() -> None:
    """Server-first chat: POST to FastAPI, consume SSE."""
    _print_banner()
    base_url = _get_base_url()
    consumer = StreamConsumer(base_url, console)

    # Create or reuse a session
    session_id: UUID | None = None

    async def _create_session() -> UUID:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{base_url}/sessions", json={"agent": "build"})
            resp.raise_for_status()
            return UUID(resp.json()["id"])

    while True:
        try:
            user_input = console.input("[bold blue]You > [/bold blue]").strip()

            if not user_input:
                continue
            if user_input.lower() in ("quit", "exit", "q", "bye"):
                console.print("\n[dim]👋 Goodbye![/dim]")
                raise typer.Exit()

            if session_id is None:
                session_id = asyncio.run(_create_session())

            # POST message + consume SSE stream in one async block
            async def _send_and_consume() -> None:
                async with httpx.AsyncClient() as client:
                    await client.post(
                        f"{base_url}/sessions/{session_id}/messages",
                        json={"content": user_input},
                    )
                # Static thinking indicator — tokens stream above it.
                # Using raw stdout in consumer avoids Rich cursor fights.
                console.print("[dim]Thinking...[/dim]")
                await consumer.consume(session_id)
                console.print()  # newline after response

            asyncio.run(_send_and_consume())

        except KeyboardInterrupt:
            console.print("\n[dim]👋 Goodbye![/dim]")
            raise typer.Exit()
        except typer.Exit:
            raise
        except Exception as exc:
            console.print(f"\n[error]Error: {exc}[/error]\n")


def _chat_direct() -> None:
    """Direct-mode chat (backward compat, no server required)."""
    from src.graph.graph import build_graph
    from src.graph.runner import invoke_agent

    _print_banner()
    console.print("\n[info]Building agent graph (direct mode)...[/info]")
    graph = build_graph()
    console.print("[success]✓ Agent ready![/success]\n")

    while True:
        try:
            user_input = console.input("[bold blue]You > [/bold blue]").strip()

            if not user_input:
                continue
            if user_input.lower() in ("quit", "exit", "q", "bye"):
                console.print("\n[dim]👋 Goodbye![/dim]")
                raise typer.Exit()

            with console.status("[agent]🤖 Thinking...[/agent]", spinner="dots"):
                response = invoke_agent(graph, user_input, thread_id="chat_session")

            console.print()
            console.print(
                Panel(Markdown(response), border_style="magenta", title="🤖 DeployAI")
            )
            console.print()

        except KeyboardInterrupt:
            console.print("\n[dim]👋 Goodbye![/dim]")
            raise typer.Exit()
        except typer.Exit:
            raise
        except Exception as exc:
            console.print(f"\n[error]Error: {exc}[/error]\n")


@app.command()
def run(
    message: str = typer.Argument(help="The request to send to the AI agent"),
    direct: bool = typer.Option(False, "--direct", help="Run graph directly without the HTTP server"),
) -> None:
    """⚡ Send a single request to DeployAI and get a response."""
    if direct:
        _run_direct(message)
        return

    _run_server(message)


def _run_server(message: str) -> None:
    """Server-first one-shot."""
    base_url = _get_base_url()
    consumer = StreamConsumer(base_url, console)

    async def _go() -> None:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{base_url}/sessions", json={"agent": "build"})
            resp.raise_for_status()
            session_id = UUID(resp.json()["id"])

            await client.post(
                f"{base_url}/sessions/{session_id}/messages",
                json={"content": message},
            )

            await consumer.consume(session_id)

    asyncio.run(_go())


def _run_direct(message: str) -> None:
    """Direct one-shot (backward compat)."""
    from src.graph.graph import build_graph
    from src.graph.runner import invoke_agent

    console.print("[info]Building agent graph (direct mode)...[/info]")
    graph = build_graph()

    with console.status("[agent]🤖 Working...[/agent]", spinner="dots"):
        response = invoke_agent(graph, message, thread_id="run_session")

    console.print()
    console.print(
        Panel(Markdown(response), border_style="magenta", title="🤖 DeployAI")
    )


@app.command()
def status() -> None:
    """📊 Check if DeployAI is configured correctly."""
    import os

    from src.core.config import get_settings

    cfg = get_settings()

    console.print(Panel("[bold]DeployAI Configuration Status[/bold]", border_style="cyan"))

    # Check LLM provider
    provider = cfg.resolved_llm_provider
    has_key = bool(cfg.gemini_api_key or cfg.openrouter_api_key or cfg.ollama_base_url)
    if has_key:
        console.print(f"  [success]✓[/success] LLM provider: {provider} ({cfg.llm_model})")
    else:
        console.print("  [error]✗[/error] No LLM API key configured (check .env)")

    # Check database
    try:
        import psycopg2

        conn = psycopg2.connect(cfg.database_url)
        conn.close()
        console.print("  [success]✓[/success] Database connection OK")
    except Exception as exc:
        console.print(f"  [error]✗[/error] Database connection failed: {exc}")

    # Check SSH key
    key_path = os.path.expanduser(cfg.ssh_key_path)
    if os.path.exists(key_path):
        console.print(f"  [success]✓[/success] SSH key found at {key_path}")
    else:
        console.print(f"  [warning]⚠[/warning] SSH key not found at {key_path}")

    # Summary
    db_host = cfg.database_url.split("@")[1] if "@" in cfg.database_url else "N/A"
    console.print(f"\n  [dim]DB: {db_host}[/dim]")


@app.command()
def mcp(
    transport: str = typer.Option(
        "stdio",
        help="Transport mode: 'stdio' for local clients, 'sse' for Docker/remote",
    ),
) -> None:
    """🔌 Start the MCP (Model Context Protocol) server."""
    from src.mcp_server.server import mcp as mcp_server

    console.print(
        Panel(
            f"[bold magenta]🔌 DeployAI MCP Server[/bold magenta]\n"
            f"[dim]Transport: {transport}[/dim]\n"
            f"[dim]Tools: ssh_execute, get_server_info, list_all_servers[/dim]",
            border_style="magenta",
            padding=(1, 2),
        )
    )

    if transport == "sse":
        console.print("[info]Starting SSE server on http://0.0.0.0:8811 ...[/info]")
    else:
        console.print("[info]Starting stdio transport...[/info]")

    mcp_server.run(transport=transport)


# ──────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────

if __name__ == "__main__":
    app()
