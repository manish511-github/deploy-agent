"""
Database Tool — Query the existing linux-server-manager PostgreSQL.

Connects to the same PostgreSQL used by your Node.js backend to look up
server information. This gives the AI agent knowledge about enrolled servers.
"""

from __future__ import annotations

import psycopg2
import psycopg2.extras
from langchain_core.tools import tool

from src.config import settings


def _get_connection():
    """Get a database connection."""
    return psycopg2.connect(settings.database_url)


@tool
def get_server_info(identifier: str) -> str:
    """
    Look up a server by hostname, server ID, or IP address from the database.

    Use this tool when the user mentions a specific server and you need to find
    its IP address, status, OS info, or other details before SSHing into it.

    Args:
        identifier: The server's hostname, server_id, or IP address.

    Returns:
        Server details including hostname, IP, OS, status, and enrollment info.
        Returns an error message if the server is not found.
    """
    try:
        conn = _get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute(
            """
            SELECT server_id, name, hostname, ip_address, public_ip_address,
                   os_name, os_version, server_status, agent_version,
                   agent_status, last_seen_at, enrolled_at, mqtt_topic
            FROM server
            WHERE hostname ILIKE %s
               OR server_id = %s
               OR ip_address = %s
               OR name ILIKE %s
            LIMIT 1
            """,
            (f"%{identifier}%", identifier, identifier, f"%{identifier}%"),
        )

        row = cursor.fetchone()
        cursor.close()
        conn.close()

        if not row:
            return f"No server found matching '{identifier}'. Use list_all_servers to see available servers."

        lines = [f"=== Server: {row['name']} ==="]
        for key, value in row.items():
            if value is not None:
                label = key.replace("_", " ").title()
                lines.append(f"  {label}: {value}")

        return "\n".join(lines)

    except psycopg2.OperationalError as e:
        return f"ERROR: Database connection failed: {e}"
    except Exception as e:
        return f"ERROR: Failed to query server info: {e}"


@tool
def list_all_servers() -> str:
    """
    List all enrolled servers with their current status.

    Use this tool when the user asks to see all servers, or when you need
    to find which servers are available before performing an action.

    Returns:
        A formatted table of all servers with hostname, IP, OS, and status.
    """
    try:
        conn = _get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute(
            """
            SELECT server_id, name, hostname, ip_address, os_name, 
                   os_version, server_status, last_seen_at
            FROM server 
            ORDER BY name
            """
        )

        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        if not rows:
            return "No servers found in the database. Enroll a server first using the linux-server-manager API."

        lines = [f"Found {len(rows)} server(s):\n"]
        for i, row in enumerate(rows, 1):
            status_emoji = {"active": "🟢", "offline": "🔴", "pending": "🟡", "error": "🔴"}.get(
                row.get("server_status", ""), "⚪"
            )
            lines.append(
                f"  {i}. {status_emoji} {row['name']} ({row['hostname']})\n"
                f"     IP: {row['ip_address']}  |  "
                f"OS: {row.get('os_name', 'N/A')} {row.get('os_version', '')}  |  "
                f"Status: {row.get('server_status', 'unknown')}"
            )

        return "\n".join(lines)

    except psycopg2.OperationalError as e:
        return f"ERROR: Database connection failed: {e}"
    except Exception as e:
        return f"ERROR: Failed to list servers: {e}"
