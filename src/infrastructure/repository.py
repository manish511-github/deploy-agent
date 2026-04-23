"""
Database repository — clean data-access layer using the Repository Pattern.

All SQL queries are isolated here. The rest of the application never sees
raw SQL or database connections; they interact through typed methods.

Uses psycopg2 with a simple connection-per-call pattern for now. Can be
swapped to asyncpg later without touching any callers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import psycopg2
import psycopg2.extras

from src.core.config import get_settings
from src.core.exceptions import DatabaseError, ServerNotFoundError


# ──────────────────────────────────────────────
# Domain models (pure data — no ORM dependency)
# ──────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Server:
    """Immutable representation of a server from the inventory."""

    server_id: str
    name: str
    hostname: str
    ip_address: str
    public_ip_address: str | None = None
    os_name: str | None = None
    os_version: str | None = None
    server_status: str = "unknown"
    agent_version: str | None = None
    agent_status: str | None = None
    last_seen_at: datetime | None = None
    enrolled_at: datetime | None = None
    mqtt_topic: str | None = None


# ──────────────────────────────────────────────
# Repository interface (Dependency Inversion)
# ──────────────────────────────────────────────


class IServerRepository(Protocol):
    """Abstract interface for server data access.

    Any class implementing this protocol can be injected as the
    repository — enabling test doubles and alternate backends.
    """

    def get_by_identifier(self, identifier: str) -> Server | None:
        """Look up a server by hostname, ID, IP, or name fragment."""
        ...

    def list_all(self) -> list[Server]:
        """Return all enrolled servers, ordered by name."""
        ...

    def resolve_ip(self, name_or_ip: str) -> str | None:
        """Resolve a server name/hostname to its IP address."""
        ...


# ──────────────────────────────────────────────
# Concrete PostgreSQL implementation
# ──────────────────────────────────────────────


class PostgresServerRepository:
    """PostgreSQL-backed implementation of the server repository."""

    def __init__(self, database_url: str | None = None) -> None:
        self._database_url = database_url or get_settings().database_url

    def _connect(self) -> psycopg2.extensions.connection:
        """Create a new database connection."""
        try:
            return psycopg2.connect(self._database_url)
        except psycopg2.OperationalError as exc:
            raise DatabaseError(f"Database connection failed: {exc}") from exc

    def get_by_identifier(self, identifier: str) -> Server | None:
        """Look up a server by hostname, server_id, IP address, or name."""
        sql = """
            SELECT server_id, name, hostname, ip_address, public_ip_address,
                   os_name, os_version, server_status, agent_version,
                   agent_status, last_seen_at, enrolled_at, mqtt_topic
            FROM server
            WHERE hostname ILIKE %s
               OR server_id = %s
               OR ip_address = %s
               OR name ILIKE %s
            LIMIT 1
        """
        pattern = f"%{identifier}%"
        try:
            conn = self._connect()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(sql, (pattern, identifier, identifier, pattern))
            row = cur.fetchone()
            cur.close()
            conn.close()
            return Server(**row) if row else None
        except psycopg2.Error as exc:
            raise DatabaseError(f"Failed to query server info: {exc}") from exc

    def list_all(self) -> list[Server]:
        """Return all enrolled servers ordered by name."""
        sql = """
            SELECT server_id, name, hostname, ip_address, public_ip_address,
                   os_name, os_version, server_status, agent_version,
                   agent_status, last_seen_at, enrolled_at, mqtt_topic
            FROM server
            ORDER BY name
        """
        try:
            conn = self._connect()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(sql)
            rows = cur.fetchall()
            cur.close()
            conn.close()
            return [Server(**row) for row in rows]
        except psycopg2.Error as exc:
            raise DatabaseError(f"Failed to list servers: {exc}") from exc

    def resolve_ip(self, name_or_ip: str) -> str | None:
        """Resolve a server name/hostname to its IP address."""
        server = self.get_by_identifier(name_or_ip)
        return server.ip_address if server else None
