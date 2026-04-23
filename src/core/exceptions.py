"""
Domain exceptions — typed errors for each subsystem.

Raising domain-specific exceptions instead of generic ``Exception``
enables targeted error handling and cleaner control flow.
"""

from __future__ import annotations


class DeployAIError(Exception):
    """Base exception for all DeployAI errors."""


# ── SSH ──────────────────────────────────────


class SSHError(DeployAIError):
    """Base SSH error."""


class SSHAuthenticationError(SSHError):
    """SSH authentication failed (bad key / credentials)."""


class SSHConnectionError(SSHError):
    """Could not establish SSH connection."""


class SSHTimeoutError(SSHError):
    """SSH operation timed out."""


class SSHCommandError(SSHError):
    """Remote command exited with non-zero status."""

    def __init__(self, command: str, exit_code: int, stderr: str) -> None:
        self.command = command
        self.exit_code = exit_code
        self.stderr = stderr
        super().__init__(
            f"Command '{command}' failed with exit code {exit_code}: {stderr}"
        )


# ── Database ─────────────────────────────────


class DatabaseError(DeployAIError):
    """Database operation failed."""


class ServerNotFoundError(DatabaseError):
    """Requested server does not exist in the inventory."""

    def __init__(self, identifier: str) -> None:
        self.identifier = identifier
        super().__init__(f"No server found matching '{identifier}'.")


# ── LLM ──────────────────────────────────────


class LLMError(DeployAIError):
    """LLM invocation failed."""


class LLMRateLimitError(LLMError):
    """LLM provider returned a rate-limit response."""

    def __init__(self, retry_after: float | None = None) -> None:
        self.retry_after = retry_after
        msg = "LLM rate limit exceeded."
        if retry_after:
            msg += f" Retry after {retry_after}s."
        super().__init__(msg)
