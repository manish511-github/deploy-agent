"""
SSH tool — execute commands on remote Linux servers.

This tool is a thin adapter between the LLM and the SSH infrastructure.
It resolves server names via the repository, then delegates to the SSH client.
"""

from __future__ import annotations

from langchain_core.tools import tool

from src.infrastructure.repository import PostgresServerRepository
from src.infrastructure.ssh_client import SSHClient
from src.core.exceptions import SSHError


@tool
def ssh_execute(server_ip: str, command: str, username: str | None = None) -> str:
    """Execute a shell command on a remote Linux server via SSH.

    Use this tool when you need to run a command on a server. You can pass either
    the server's IP address OR its name/hostname — it will auto-resolve.
    Common commands: uptime, free -h, df -h, docker ps, systemctl status <service>,
    cat /etc/os-release, top -bn1 | head -20, journalctl -u <service> --no-pager -n 50

    Args:
        server_ip: IP address, hostname, or server name of the target server.
        command: The shell command to execute on the server.
        username: SSH username. Defaults to configured default (usually root).

    Returns:
        Command output (stdout). If there are errors, stderr is included.
    """
    ssh = SSHClient()
    resolved_ip = server_ip

    # Auto-resolve: if it doesn't look like an IP, look it up in the DB
    if not SSHClient.is_ip_address(server_ip):
        repo = PostgresServerRepository()
        ip = repo.resolve_ip(server_ip)
        if ip is None:
            # Fall back to using the raw value (could be a Docker hostname)
            resolved_ip = server_ip
        else:
            resolved_ip = ip

    try:
        return ssh.execute(resolved_ip, command, username)
    except SSHError as exc:
        return f"ERROR: {exc}"
