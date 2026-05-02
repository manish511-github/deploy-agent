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
        "Provides agent-based script execution, server lookup, and fleet listing "
        "against a PostgreSQL-backed server inventory."
    ),
    host=_settings.mcp_host,
    port=_settings.mcp_port,
)


# ──────────────────────────────────────────────
# Tools
# ──────────────────────────────────────────────


@mcp.tool()
async def execute_agent_script(server_name: str, script: str, description: str) -> str:
    """Execute a shell script on a remote server using the Go agent queue.

    Args:
        server_name: Target server hostname or name.
        script: The full bash script to execute.
        description: Human-readable explanation of what this script does.

    Returns:
        stdout/stderr output from the script execution.
    """
    from src.tools.agent_task import execute_dynamic_script as _exec

    try:
        return await _exec.ainvoke(
            {
                "server_name": server_name,
                "script": script,
                "description": description,
                "risk_level": "medium",
            }
        )
    except Exception as exc:
        return f"ERROR: Agent execution failed: {exc}"


@mcp.tool()
async def send_agent_action(server_name: str, task_type: str, payload: dict | None = None) -> str:
    """Send a structured task (like system.info or device.lock) to the Go agent.
    
    Args:
        server_name: Target server hostname or name.
        task_type: Type of task (e.g. system.info).
        payload: Task-specific payload.
        
    Returns:
        JSON response from the agent.
    """
    from src.tools.agent_task import send_agent_task as _send

    try:
        return await _send.ainvoke(
            {
                "server_name": server_name,
                "task_type": task_type,
                "payload": payload or {},
            }
        )
    except Exception as exc:
        return f"ERROR: Task dispatch failed: {exc}"


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
        f"2. Run these diagnostic commands via execute_agent_script:\n"
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
