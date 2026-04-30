"""SSE consumer for the CLI — renders events as they arrive.

Connects to GET /sessions/:id/events and prints each event directly.
Uses Rich console for all output so wrapping and cursor tracking are
handled correctly.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator
from uuid import UUID

import httpx
from rich.console import Console
from rich.panel import Panel

from src.bus.events import Event, EventType


class StreamConsumer:
    """Consumes an SSE stream and renders events via direct console output."""

    def __init__(self, base_url: str, console: Console) -> None:
        self.base_url = base_url.rstrip("/")
        self.console = console

    async def consume(self, session_id: UUID) -> str:
        """Open SSE stream and render until DONE.

        Returns:
            The final accumulated text.
        """
        url = f"{self.base_url}/sessions/{session_id}/events"
        text_buffer = ""
        in_text_block = False

        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue

                    raw = line[len("data: "):]
                    try:
                        event = Event.parse(raw)
                    except Exception:
                        continue

                    match event.event_type:
                        case EventType.STEP_START:
                            msg = event.payload.get("message", "")
                            if msg:
                                if in_text_block:
                                    self.console.print()
                                    in_text_block = False
                                self.console.print(f"[dim]{msg}[/dim]")

                        case EventType.TEXT_DELTA:
                            token = event.payload.get("text", "")
                            if token:
                                text_buffer += token
                                # Use Rich console so wrapping is handled
                                # correctly and cursor state stays consistent.
                                self.console.print(token, end="")
                                in_text_block = True

                        case EventType.TOOL_START:
                            tool = event.payload.get("tool", "")
                            if in_text_block:
                                self.console.print()  # end current text line
                                in_text_block = False
                            self.console.print(f"\n[dim]▶ Running {tool}...[/dim]")

                        case EventType.TOOL_RESULT:
                            result = event.payload.get("result", "")
                            if in_text_block:
                                self.console.print()
                                in_text_block = False
                            self.console.print(
                                Panel(
                                    result[:800],
                                    border_style="green",
                                    title="Result",
                                )
                            )

                        case EventType.TOOL_ERROR:
                            err = event.payload.get("error", "")
                            if in_text_block:
                                self.console.print()
                                in_text_block = False
                            self.console.print(
                                Panel(err, border_style="red", title="Error")
                            )

                        case EventType.PERMISSION_ASKED:
                            request_id = event.payload.get("request_id", "")
                            permission = event.payload.get("permission", "")
                            patterns = event.payload.get("patterns", [])

                            if in_text_block:
                                self.console.print()
                                in_text_block = False

                            self.console.print(
                                Panel(
                                    f"[bold red]Permission Required[/bold red]\n\n"
                                    f"Tool: [bold]{permission}[/bold]\n"
                                    f"Patterns: {', '.join(patterns)}",
                                    border_style="yellow",
                                )
                            )

                            reply = self._ask_permission(request_id, permission)
                            await self._send_reply(request_id, reply)

                        case EventType.DONE:
                            if in_text_block:
                                self.console.print()
                            return text_buffer

                        case EventType.ERROR:
                            err = event.payload.get("error", "Unknown error")
                            if in_text_block:
                                self.console.print()
                                in_text_block = False
                            self.console.print(f"\n[bold red]Error: {err}[/bold red]")
                            return text_buffer

        return text_buffer

    def _ask_permission(
        self, request_id: str, permission: str
    ) -> str:
        """Prompt user for permission. Returns 'once', 'always', or 'reject'."""
        import typer

        self.console.print("[a]llow once  [A]llow always  [r]eject")
        choice = self.console.input("> ").strip().lower()

        if choice == "a":
            return "once"
        if choice == "A" or choice == "always":
            return "always"
        return "reject"

    async def _send_reply(self, request_id: str, reply: str) -> None:
        """POST the user's reply to the server."""
        url = f"{self.base_url}/permissions/{request_id}/reply"
        async with httpx.AsyncClient() as client:
            try:
                await client.post(url, json={"reply": reply})
            except Exception as exc:
                self.console.print(f"[dim]Failed to send reply: {exc}[/dim]")
