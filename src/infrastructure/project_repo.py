"""
Project repository — CRUD for projects and environments.

No K8s calls here — pure DB state tracking.
K8s namespace creation is handled by the Go agent via MQTT.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import psycopg2
import psycopg2.extras

from src.core.config import get_settings
from src.core.exceptions import DatabaseError


# ── Domain models ─────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Project:
    id: UUID
    name: str
    description: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Environment:
    id: UUID
    project_id: UUID
    name: str
    namespace: str
    server_id: str | None
    is_default: bool
    created_at: datetime


# ── Repository ────────────────────────────────────────────────────────────────


class PostgresProjectRepository:

    def __init__(self, database_url: str | None = None) -> None:
        self._database_url = database_url or get_settings().database_url

    def _connect(self):
        try:
            return psycopg2.connect(self._database_url)
        except psycopg2.OperationalError as exc:
            raise DatabaseError(f"Database connection failed: {exc}") from exc

    # ── Projects ──────────────────────────────────

    def get_project(self, name: str) -> Project | None:
        sql = "SELECT id, name, description, created_at FROM projects WHERE name = %s"
        try:
            with self._connect() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(sql, (name,))
                    row = cur.fetchone()
            return Project(**row) if row else None
        except psycopg2.Error as exc:
            raise DatabaseError(f"get_project failed: {exc}") from exc

    def get_or_create_project(self, name: str, description: str | None = None) -> Project:
        """Return existing project or create it — idempotent."""
        sql = """
            INSERT INTO projects (name, description)
            VALUES (%s, %s)
            ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
            RETURNING id, name, description, created_at
        """
        try:
            with self._connect() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(sql, (name, description))
                    row = cur.fetchone()
                conn.commit()
            return Project(**row)
        except psycopg2.Error as exc:
            raise DatabaseError(f"get_or_create_project failed: {exc}") from exc

    def delete_project(self, name: str) -> bool:
        sql = "DELETE FROM projects WHERE name = %s RETURNING id"
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (name,))
                    deleted = cur.fetchone() is not None
                conn.commit()
            return deleted
        except psycopg2.Error as exc:
            raise DatabaseError(f"delete_project failed: {exc}") from exc

    # ── Environments ──────────────────────────────

    def get_environment(self, namespace: str) -> Environment | None:
        """Look up an environment by its K8s namespace string."""
        sql = """
            SELECT id, project_id, name, namespace, server_id, is_default, created_at
            FROM environments WHERE namespace = %s
        """
        try:
            with self._connect() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(sql, (namespace,))
                    row = cur.fetchone()
            return Environment(**row) if row else None
        except psycopg2.Error as exc:
            raise DatabaseError(f"get_environment failed: {exc}") from exc

    def get_environment_by_name(self, project_name: str, env_name: str) -> Environment | None:
        """Look up environment by project name + environment name."""
        sql = """
            SELECT e.id, e.project_id, e.name, e.namespace,
                   e.server_id, e.is_default, e.created_at
            FROM environments e
            JOIN projects p ON p.id = e.project_id
            WHERE p.name = %s AND e.name = %s
        """
        try:
            with self._connect() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(sql, (project_name, env_name))
                    row = cur.fetchone()
            return Environment(**row) if row else None
        except psycopg2.Error as exc:
            raise DatabaseError(f"get_environment_by_name failed: {exc}") from exc

    def get_default_environment(self, server_id: str) -> Environment | None:
        """Return the default environment for a given server."""
        sql = """
            SELECT id, project_id, name, namespace, server_id, is_default, created_at
            FROM environments
            WHERE server_id = %s AND is_default = TRUE
            LIMIT 1
        """
        try:
            with self._connect() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(sql, (server_id,))
                    row = cur.fetchone()
            return Environment(**row) if row else None
        except psycopg2.Error as exc:
            raise DatabaseError(f"get_default_environment failed: {exc}") from exc

    def get_or_create_environment(
        self,
        project_id: str,
        name: str,
        namespace: str,
        server_id: str | None = None,
        is_default: bool = False,
    ) -> Environment:
        """Return existing environment or create it — idempotent."""
        sql = """
            INSERT INTO environments (project_id, name, namespace, server_id, is_default)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (namespace) DO UPDATE SET
                server_id  = EXCLUDED.server_id,
                is_default = EXCLUDED.is_default
            RETURNING id, project_id, name, namespace, server_id, is_default, created_at
        """
        try:
            with self._connect() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(sql, (project_id, name, namespace, server_id, is_default))
                    row = cur.fetchone()
                conn.commit()
            return Environment(**row)
        except psycopg2.Error as exc:
            raise DatabaseError(f"get_or_create_environment failed: {exc}") from exc

    def list_environments(self, project_id: str) -> list[Environment]:
        sql = """
            SELECT id, project_id, name, namespace, server_id, is_default, created_at
            FROM environments WHERE project_id = %s ORDER BY is_default DESC, name
        """
        try:
            with self._connect() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(sql, (project_id,))
                    rows = cur.fetchall()
            return [Environment(**row) for row in rows]
        except psycopg2.Error as exc:
            raise DatabaseError(f"list_environments failed: {exc}") from exc
