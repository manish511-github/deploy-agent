"""
Fleet repository — server inventory data access layer.

Uses psycopg2 with context managers for safe connection handling.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import psycopg2
import psycopg2.extras

from src.core.config import get_settings
from src.core.exceptions import DatabaseError


# ──────────────────────────────────────────────
# Domain models
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
# Repository interface
# ──────────────────────────────────────────────


class IServerRepository(Protocol):
    def get_by_identifier(self, identifier: str) -> Server | None: ...
    def list_all(self) -> list[Server]: ...
    def resolve_ip(self, name_or_ip: str) -> str | None: ...


# ──────────────────────────────────────────────
# Concrete PostgreSQL implementation
# ──────────────────────────────────────────────

_SELECT_COLS = """
    server_id, name, hostname, ip_address, public_ip_address,
    os_name, os_version, server_status, agent_version,
    agent_status, last_seen_at, enrolled_at, mqtt_topic
"""


class PostgresServerRepository:
    """PostgreSQL-backed server repository."""

    def __init__(self, database_url: str | None = None) -> None:
        self._database_url = database_url or get_settings().database_url

    def _connect(self) -> psycopg2.extensions.connection:
        try:
            return psycopg2.connect(self._database_url)
        except psycopg2.OperationalError as exc:
            raise DatabaseError(f"Database connection failed: {exc}") from exc

    def get_by_identifier(self, identifier: str) -> Server | None:
        sql = f"""
            SELECT {_SELECT_COLS}
            FROM server
            WHERE hostname ILIKE %s
               OR server_id = %s
               OR ip_address = %s
               OR name ILIKE %s
            LIMIT 1
        """
        pattern = f"%{identifier}%"
        try:
            with self._connect() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(sql, (pattern, identifier, identifier, pattern))
                    row = cur.fetchone()
            return Server(**row) if row else None
        except psycopg2.Error as exc:
            raise DatabaseError(f"Failed to query server info: {exc}") from exc

    def list_all(self) -> list[Server]:
        sql = f"SELECT {_SELECT_COLS} FROM server ORDER BY name"
        try:
            with self._connect() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(sql)
                    rows = cur.fetchall()
            return [Server(**row) for row in rows]
        except psycopg2.Error as exc:
            raise DatabaseError(f"Failed to list servers: {exc}") from exc

    def resolve_ip(self, name_or_ip: str) -> str | None:
        server = self.get_by_identifier(name_or_ip)
        return server.ip_address if server else None
