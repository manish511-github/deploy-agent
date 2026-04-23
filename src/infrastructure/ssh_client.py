"""
SSH client — encapsulated SSH operations.

Wraps paramiko behind a clean interface so callers don't deal with
low-level connection setup, key handling, or error translation.
"""

from __future__ import annotations

import os
import re

import paramiko

from src.core.config import get_settings
from src.core.exceptions import (
    SSHAuthenticationError,
    SSHCommandError,
    SSHConnectionError,
    SSHTimeoutError,
)


class SSHClient:
    """Manages SSH connections and command execution on remote servers."""

    def __init__(
        self,
        key_path: str | None = None,
        default_user: str | None = None,
        timeout: int | None = None,
    ) -> None:
        settings = get_settings()
        self._key_path = os.path.expanduser(key_path or settings.ssh_key_path)
        self._default_user = default_user or settings.ssh_default_user
        self._timeout = timeout or settings.ssh_timeout

    def _create_connection(
        self, host: str, username: str | None = None
    ) -> paramiko.SSHClient:
        """Create and return a connected paramiko SSH client."""
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        user = username or self._default_user
        connect_kwargs: dict = {
            "hostname": host,
            "username": user,
            "timeout": self._timeout,
        }

        if os.path.exists(self._key_path):
            connect_kwargs["key_filename"] = self._key_path
        else:
            connect_kwargs["allow_agent"] = True

        try:
            client.connect(**connect_kwargs)
        except paramiko.AuthenticationException as exc:
            raise SSHAuthenticationError(
                f"Authentication failed for {user}@{host}. Check SSH key."
            ) from exc
        except paramiko.SSHException as exc:
            raise SSHConnectionError(
                f"SSH connection error to {host}: {exc}"
            ) from exc
        except TimeoutError as exc:
            raise SSHTimeoutError(
                f"Connection to {host} timed out after {self._timeout}s."
            ) from exc

        return client

    def execute(
        self, host: str, command: str, username: str | None = None
    ) -> str:
        """Execute a shell command on a remote host and return the output.

        Args:
            host: IP address or hostname of the target server.
            command: Shell command to execute.
            username: SSH user (defaults to config value).

        Returns:
            Combined stdout/stderr output.

        Raises:
            SSHAuthenticationError: If authentication fails.
            SSHConnectionError: If the connection cannot be established.
            SSHTimeoutError: If the connection or command times out.
        """
        client = self._create_connection(host, username)

        try:
            _, stdout, stderr = client.exec_command(
                command, timeout=self._timeout
            )

            out = stdout.read().decode("utf-8", errors="replace").strip()
            err = stderr.read().decode("utf-8", errors="replace").strip()
            exit_code = stdout.channel.recv_exit_status()

            parts: list[str] = []
            if out:
                parts.append(out)
            if err:
                parts.append(f"[STDERR]: {err}")
            if exit_code != 0:
                parts.append(f"[EXIT CODE]: {exit_code}")

            return "\n".join(parts) or "(no output)"

        except Exception as exc:
            if isinstance(exc, (SSHAuthenticationError, SSHConnectionError, SSHTimeoutError)):
                raise
            raise SSHConnectionError(
                f"Failed to execute command on {host}: {exc}"
            ) from exc
        finally:
            client.close()

    @staticmethod
    def is_ip_address(value: str) -> bool:
        """Check if a string looks like an IPv4 address."""
        return bool(
            re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", value)
        )
