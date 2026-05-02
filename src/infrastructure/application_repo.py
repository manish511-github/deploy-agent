"""
Application repository — CRUD for applications and k8s_resources.

Pure DB state tracking; no K8s calls.
K8s operations are sent via MQTT to the Go agent.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg2
import psycopg2.extras

from src.core.config import get_settings
from src.core.exceptions import DatabaseError


# ── Domain models ─────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Application:
    id: UUID
    name: str
    environment_id: UUID
    image: str
    replicas: int
    status: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class K8sResource:
    id: UUID
    application_id: UUID
    resource_type: str
    resource_name: str
    namespace: str
    manifest: dict[str, Any]
    created_at: datetime


# ── Repository ────────────────────────────────────────────────────────────────


class PostgresApplicationRepository:

    def __init__(self, database_url: str | None = None) -> None:
        self._database_url = database_url or get_settings().database_url

    def _connect(self):
        try:
            return psycopg2.connect(self._database_url)
        except psycopg2.OperationalError as exc:
            raise DatabaseError(f"Database connection failed: {exc}") from exc

    # ── Applications ──────────────────────────────

    def get_app(self, name: str, environment_id: str) -> Application | None:
        sql = """
            SELECT id, name, environment_id, image, replicas, status, created_at
            FROM applications
            WHERE name = %s AND environment_id = %s
        """
        try:
            with self._connect() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(sql, (name, environment_id))
                    row = cur.fetchone()
            return Application(**row) if row else None
        except psycopg2.Error as exc:
            raise DatabaseError(f"get_app failed: {exc}") from exc

    def list_apps(self, environment_id: str) -> list[Application]:
        sql = """
            SELECT id, name, environment_id, image, replicas, status, created_at
            FROM applications WHERE environment_id = %s ORDER BY name
        """
        try:
            with self._connect() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(sql, (environment_id,))
                    rows = cur.fetchall()
            return [Application(**row) for row in rows]
        except psycopg2.Error as exc:
            raise DatabaseError(f"list_apps failed: {exc}") from exc

    def create_app(
        self,
        name: str,
        environment_id: str,
        image: str,
        replicas: int = 1,
    ) -> Application:
        sql = """
            INSERT INTO applications (name, environment_id, image, replicas, status)
            VALUES (%s, %s, %s, %s, 'deploying')
            ON CONFLICT (name, environment_id) DO UPDATE SET
                image    = EXCLUDED.image,
                replicas = EXCLUDED.replicas,
                status   = 'deploying'
            RETURNING id, name, environment_id, image, replicas, status, created_at
        """
        try:
            with self._connect() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(sql, (name, environment_id, image, replicas))
                    row = cur.fetchone()
                conn.commit()
            return Application(**row)
        except psycopg2.Error as exc:
            raise DatabaseError(f"create_app failed: {exc}") from exc

    def update_status(self, app_id: str, status: str) -> None:
        sql = "UPDATE applications SET status = %s WHERE id = %s"
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (status, app_id))
                conn.commit()
        except psycopg2.Error as exc:
            raise DatabaseError(f"update_status failed: {exc}") from exc

    def update_replicas(self, app_id: str, replicas: int) -> None:
        sql = "UPDATE applications SET replicas = %s WHERE id = %s"
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (replicas, app_id))
                conn.commit()
        except psycopg2.Error as exc:
            raise DatabaseError(f"update_replicas failed: {exc}") from exc

    def delete_app(self, app_id: str) -> None:
        sql = "DELETE FROM applications WHERE id = %s"
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (app_id,))
                conn.commit()
        except psycopg2.Error as exc:
            raise DatabaseError(f"delete_app failed: {exc}") from exc

    # ── K8s resources ─────────────────────────────

    def track_resource(
        self,
        application_id: str,
        resource_type: str,
        resource_name: str,
        namespace: str,
        manifest: dict[str, Any] | None = None,
    ) -> None:
        sql = """
            INSERT INTO k8s_resources (application_id, resource_type, resource_name, namespace, manifest)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (application_id, resource_type, resource_name) DO UPDATE SET
                namespace = EXCLUDED.namespace,
                manifest  = EXCLUDED.manifest
        """
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (
                        application_id, resource_type, resource_name,
                        namespace, psycopg2.extras.Json(manifest or {}),
                    ))
                conn.commit()
        except psycopg2.Error as exc:
            raise DatabaseError(f"track_resource failed: {exc}") from exc

    def delete_resources_for_app(self, application_id: str) -> None:
        sql = "DELETE FROM k8s_resources WHERE application_id = %s"
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (application_id,))
                conn.commit()
        except psycopg2.Error as exc:
            raise DatabaseError(f"delete_resources_for_app failed: {exc}") from exc
