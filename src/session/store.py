"""Session and message persistence layer.

Uses asyncpg for all CRUD. Messages are stored as structured JSONB
``parts`` arrays so they are queryable and version-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import asyncpg


# ──────────────────────────────────────────────
# Domain models
# ──────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Session:
    id: UUID
    parent_id: UUID | None
    agent: str
    title: str | None
    status: str  # active | compacted | archived | errored
    model: str
    total_tokens_in: int
    total_tokens_out: int
    total_cost_usd: float
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class Message:
    id: UUID
    session_id: UUID
    role: str  # user | assistant | tool | system
    parts: list[dict[str, Any]]
    usage: dict[str, Any] | None
    created_at: datetime


# ──────────────────────────────────────────────
# Store
# ──────────────────────────────────────────────


class SessionStore:
    """Async session/message CRUD on Postgres."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    # ── Sessions ───────────────────────────────────────────

    async def create_session(
        self,
        agent: str = "build",
        model: str = "gemini-2.5-flash-lite",
        title: str | None = None,
        parent_id: UUID | None = None,
    ) -> Session:
        """INSERT a new session row."""
        sql = """
            INSERT INTO sessions (id, parent_id, agent, title, status, model,
                                  total_tokens_in, total_tokens_out, total_cost_usd,
                                  created_at, updated_at)
            VALUES ($1, $2, $3, $4, 'active', $5, 0, 0, 0.0, NOW(), NOW())
            RETURNING id, parent_id, agent, title, status, model,
                      total_tokens_in, total_tokens_out, total_cost_usd,
                      created_at, updated_at
        """
        sid = uuid4()
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(sql, sid, parent_id, agent, title, model)
        return self._row_to_session(row)

    async def get_session(self, session_id: UUID) -> Session | None:
        """SELECT a session by id."""
        sql = """
            SELECT id, parent_id, agent, title, status, model,
                   total_tokens_in, total_tokens_out, total_cost_usd,
                   created_at, updated_at
            FROM sessions WHERE id = $1
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(sql, session_id)
        return self._row_to_session(row) if row else None

    async def list_sessions(self, limit: int = 50) -> list[Session]:
        """List recent sessions."""
        sql = """
            SELECT id, parent_id, agent, title, status, model,
                   total_tokens_in, total_tokens_out, total_cost_usd,
                   created_at, updated_at
            FROM sessions ORDER BY updated_at DESC LIMIT $1
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, limit)
        return [self._row_to_session(r) for r in rows]

    async def update_session_title(self, session_id: UUID, title: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE sessions SET title = $1, updated_at = NOW() WHERE id = $2",
                title, session_id,
            )

    async def update_session_status(self, session_id: UUID, status: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE sessions SET status = $1, updated_at = NOW() WHERE id = $2",
                status, session_id,
            )

    async def update_session_usage(
        self,
        session_id: UUID,
        tokens_in: int,
        tokens_out: int,
        cost_usd: float,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """UPDATE sessions
                   SET total_tokens_in = total_tokens_in + $1,
                       total_tokens_out = total_tokens_out + $2,
                       total_cost_usd = total_cost_usd + $3,
                       updated_at = NOW()
                   WHERE id = $4""",
                tokens_in, tokens_out, cost_usd, session_id,
            )

    # ── Messages ───────────────────────────────────────────

    async def add_message(
        self,
        session_id: UUID,
        role: str,
        parts: list[dict[str, Any]],
        usage: dict[str, Any] | None = None,
    ) -> Message:
        """Append a message to the session log."""
        sql = """
            INSERT INTO messages (id, session_id, role, parts, usage, created_at)
            VALUES ($1, $2, $3, $4, $5, NOW())
            RETURNING id, session_id, role, parts, usage, created_at
        """
        mid = uuid4()
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(sql, mid, session_id, role, json.dumps(parts), json.dumps(usage) if usage else None)
        return self._row_to_message(row)

    async def list_messages(self, session_id: UUID) -> list[Message]:
        """Ordered message history for a session."""
        sql = """
            SELECT id, session_id, role, parts, usage, created_at
            FROM messages WHERE session_id = $1 ORDER BY created_at ASC
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, session_id)
        return [self._row_to_message(r) for r in rows]

    async def get_messages_since(self, session_id: UUID, since: datetime) -> list[Message]:
        """Messages created after a given time (for SSE replay)."""
        sql = """
            SELECT id, session_id, role, parts, usage, created_at
            FROM messages WHERE session_id = $1 AND created_at > $2 ORDER BY created_at ASC
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, session_id, since)
        return [self._row_to_message(r) for r in rows]

    # ── Helpers ────────────────────────────────────────────

    @staticmethod
    def _row_to_session(row: asyncpg.Record) -> Session:
        return Session(
            id=row["id"],
            parent_id=row["parent_id"],
            agent=row["agent"],
            title=row["title"],
            status=row["status"],
            model=row["model"],
            total_tokens_in=row["total_tokens_in"],
            total_tokens_out=row["total_tokens_out"],
            total_cost_usd=float(row["total_cost_usd"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_message(row: asyncpg.Record) -> Message:
        return Message(
            id=row["id"],
            session_id=row["session_id"],
            role=row["role"],
            parts=row["parts"] if isinstance(row["parts"], list) else json.loads(row["parts"] or "[]"),
            usage=row["usage"] if isinstance(row["usage"], dict) else (json.loads(row["usage"]) if row["usage"] else None),
            created_at=row["created_at"],
        )


import json
