"""
Database tools — query the server inventory.

Thin adapters between the LLM and the PostgresServerRepository.
Tools format repository data into human-readable strings.
"""

from __future__ import annotations

from langchain_core.tools import tool

from src.infrastructure.repository import PostgresServerRepository
from src.core.exceptions import DatabaseError


def _format_server(server) -> str:
    """Format a Server dataclass into a readable string."""
    lines = [f"=== Server: {server.name} ==="]
    for field_name in server.__dataclass_fields__:
        value = getattr(server, field_name)
        if value is not None:
            label = field_name.replace("_", " ").title()
            lines.append(f"  {label}: {value}")
    return "\n".join(lines)


@tool
def get_server_info(identifier: str) -> str:
    """Look up a server by hostname, server ID, or IP address from the database.

    Use this tool when the user mentions a specific server and you need to find
    its IP address, status, OS info, or other details before SSHing into it.

    Args:
        identifier: The server's hostname, server_id, or IP address.

    Returns:
        Server details including hostname, IP, OS, status, and enrollment info.
        Returns an error message if the server is not found.
    """
    try:
        repo = PostgresServerRepository()
        server = repo.get_by_identifier(identifier)

        if server is None:
            return (
                f"No server found matching '{identifier}'. "
                "Use list_all_servers to see available servers."
            )

        return _format_server(server)

    except DatabaseError as exc:
        return f"ERROR: {exc}"


@tool
def list_all_servers() -> str:
    """List all enrolled servers with their current status.

    Use this tool when the user asks to see all servers, or when you need
    to find which servers are available before performing an action.

    Returns:
        A formatted table of all servers with hostname, IP, OS, and status.
    """
    try:
        repo = PostgresServerRepository()
        servers = repo.list_all()

        if not servers:
            return (
                "No servers found in the database. "
                "Enroll a server first using the linux-server-manager API."
            )

        status_icons = {
            "active": "🟢",
            "offline": "🔴",
            "pending": "🟡",
            "error": "🔴",
        }

        lines = [f"Found {len(servers)} server(s):\n"]
        for i, s in enumerate(servers, 1):
            icon = status_icons.get(s.server_status, "⚪")
            lines.append(
                f"  {i}. {icon} {s.name} ({s.hostname})\n"
                f"     IP: {s.ip_address}  |  "
                f"OS: {s.os_name or 'N/A'} {s.os_version or ''}  |  "
                f"Status: {s.server_status}"
            )

        return "\n".join(lines)

    except DatabaseError as exc:
        return f"ERROR: {exc}"
