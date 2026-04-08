"""
SSH Tool — Execute commands on remote Linux servers.

Uses paramiko to establish SSH connections and run shell commands.
This is the primary tool for interacting with target servers.
"""

from __future__ import annotations

import os

import paramiko
from langchain_core.tools import tool
from langgraph.types import interrupt

from src.config import settings


def _get_ssh_client(server_ip: str, username: str | None = None) -> paramiko.SSHClient:
    """Create and configure an SSH client connection."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    ssh_user = username or settings.ssh_default_user
    key_path = os.path.expanduser(settings.ssh_key_path)

    connect_kwargs: dict = {
        "hostname": server_ip,
        "username": ssh_user,
        "timeout": settings.ssh_timeout,
    }

    # Use key-based auth if key exists, otherwise fall back to agent
    if os.path.exists(key_path):
        connect_kwargs["key_filename"] = key_path
    else:
        connect_kwargs["allow_agent"] = True

    client.connect(**connect_kwargs)
    return client


@tool
def ssh_execute(server_ip: str, command: str, username: str | None = None) -> str:
    """
    Execute a shell command on a remote Linux server via SSH.

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
    # Auto-resolve: if server_ip doesn't look like an IP, look it up in the DB
    resolved_ip = server_ip
    if not _looks_like_ip(server_ip):
        resolved_ip = _resolve_server_ip(server_ip)
        if resolved_ip is None:
            return f"ERROR: Could not find server '{server_ip}' in the database."

    # removed interrupt block as it breaks create_react_agent tool execution

    try:
        client = _get_ssh_client(resolved_ip, username)
        stdin, stdout, stderr = client.exec_command(command, timeout=settings.ssh_timeout)

        out = stdout.read().decode("utf-8", errors="replace").strip()
        err = stderr.read().decode("utf-8", errors="replace").strip()
        exit_code = stdout.channel.recv_exit_status()
        client.close()

        result = ""
        if out:
            result += out
        if err:
            result += f"\n[STDERR]: {err}"
        if exit_code != 0:
            result += f"\n[EXIT CODE]: {exit_code}"

        return result or "(no output)"

    except paramiko.AuthenticationException:
        return f"ERROR: SSH authentication failed for {resolved_ip}. Check your SSH key or credentials."
    except paramiko.SSHException as e:
        return f"ERROR: SSH connection error to {resolved_ip}: {e}"
    except TimeoutError:
        return f"ERROR: SSH connection to {resolved_ip} timed out after {settings.ssh_timeout}s."
    except Exception as e:
        return f"ERROR: Failed to execute command on {resolved_ip}: {e}"


def _looks_like_ip(value: str) -> bool:
    """Check if a string looks like an IP address."""
    import re
    return bool(re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', value))


def _resolve_server_ip(name: str) -> str | None:
    """Look up a server's IP address from the database by name/hostname/ip."""
    try:
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(settings.database_url)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(
            """SELECT ip_address FROM server 
               WHERE name ILIKE %s OR hostname ILIKE %s 
               OR ip_address ILIKE %s OR server_id = %s
               LIMIT 1""",
            (f"%{name}%", f"%{name}%", f"%{name}%", name),
        )
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        return row["ip_address"] if row else None
    except Exception:
        return None
