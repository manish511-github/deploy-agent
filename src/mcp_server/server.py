"""
DeployAI MCP Server — expose infrastructure tools via Model Context Protocol.

Allows any MCP-compatible client (Claude Desktop, Cursor, Windsurf, VS Code
Copilot) to use DeployAI's SSH & database tools directly.

Transport modes:
  - stdio  (default): For local integrations (Claude Desktop, Cursor)
  - sse:   For remote/Docker integrations over HTTP
"""

from __future__ import annotations

import sys

from mcp.server.fastmcp import FastMCP

from src.core.config import get_settings

# ──────────────────────────────────────────────
# Server initialization
# ──────────────────────────────────────────────

_settings = get_settings()

mcp = FastMCP(
    "deploy-ai",
    instructions=(
        "DeployAI — AI-powered Linux server management. "
        "Provides SSH command execution, server lookup, and fleet listing "
        "against a PostgreSQL-backed server inventory."
    ),
    host=_settings.mcp_host,
    port=_settings.mcp_port,
)


# ──────────────────────────────────────────────
# Tools
# ──────────────────────────────────────────────


@mcp.tool()
def ssh_execute(server_ip: str, command: str, username: str | None = None) -> str:
    """Execute a shell command on a remote Linux server via SSH.

    Use this tool when you need to run a command on a server. You can pass
    either the server's IP address OR its name/hostname — it will auto-resolve.

    Args:
        server_ip: IP address, hostname, or server name of the target server.
        command: The shell command to execute on the server.
        username: SSH username. Defaults to configured default (usually root).

    Returns:
        Command output (stdout). If there are errors, stderr is included.
    """
    from src.tools.ssh import ssh_execute as _ssh_execute

    return _ssh_execute.invoke(
        {"server_ip": server_ip, "command": command, "username": username}
    )


@mcp.tool()
def get_server_info(identifier: str) -> str:
    """Look up a server by hostname, server ID, or IP address from the database.

    Args:
        identifier: The server's hostname, server_id, or IP address.

    Returns:
        Server details including hostname, IP, OS, status, and enrollment info.
    """
    from src.tools.database import get_server_info as _get_server_info

    return _get_server_info.invoke({"identifier": identifier})


@mcp.tool()
def list_all_servers() -> str:
    """List all enrolled servers with their current status.

    Returns:
        A formatted table of all servers with hostname, IP, OS, and status.
    """
    from src.tools.database import list_all_servers as _list_all_servers

    return _list_all_servers.invoke({})


# ──────────────────────────────────────────────
# Resources
# ──────────────────────────────────────────────


@mcp.resource("deployai://config/status")
def get_config_status() -> str:
    """Current DeployAI configuration summary."""
    import os

    cfg = get_settings()
    key_path = os.path.expanduser(cfg.ssh_key_path)
    ssh_ok = "✅" if os.path.exists(key_path) else "❌"

    return (
        f"DeployAI Configuration\n"
        f"─────────────────────\n"
        f"LLM Provider: {cfg.resolved_llm_provider}\n"
        f"LLM Model:    {cfg.llm_model}\n"
        f"SSH Key:      {ssh_ok} {key_path}\n"
        f"SSH User:     {cfg.ssh_default_user}\n"
        f"SSH Timeout:  {cfg.ssh_timeout}s\n"
    )


# ──────────────────────────────────────────────
# Prompts
# ──────────────────────────────────────────────


@mcp.prompt()
def server_health_check(server_name: str) -> str:
    """Generate a comprehensive server health check prompt."""
    return (
        f"Perform a full health check on the server '{server_name}'.\n\n"
        f"Steps:\n"
        f"1. Look up the server using get_server_info\n"
        f"2. Run these diagnostic commands via ssh_execute:\n"
        f"   - uptime\n"
        f"   - free -h\n"
        f"   - df -h\n"
        f"   - docker ps --format 'table {{{{.Names}}}}\\t{{{{.Status}}}}\\t{{{{.Ports}}}}'\n"
        f"   - systemctl list-units --state=failed --no-pager\n"
        f"3. Summarize the results, flagging any issues.\n"
    )


@mcp.prompt()
def deploy_service(server_name: str, service_name: str) -> str:
    """Generate a deployment prompt for a service on a specific server."""
    return (
        f"Deploy the service '{service_name}' on server '{server_name}'.\n\n"
        f"Steps:\n"
        f"1. Look up the server\n"
        f"2. Check if the service is already running\n"
        f"3. Pull the latest version and restart\n"
        f"4. Verify the service is healthy\n"
    )


# ──────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────

if __name__ == "__main__":
    transport = "stdio"
    if "--transport" in sys.argv:
        idx = sys.argv.index("--transport")
        if idx + 1 < len(sys.argv):
            transport = sys.argv[idx + 1]

    mcp.run(transport=transport)
