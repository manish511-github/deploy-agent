"""
Backward-compatibility shim — import from src.fleet.repository in new code.
"""

from src.fleet.repository import (  # noqa: F401
    IServerRepository,
    PostgresServerRepository,
    Server,
)
