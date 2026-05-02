"""
Async database pool — asyncpg-backed connection pool.

Usage:
    from src.core.db import get_pool

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT 1")

The pool is created once per process and reused. Call close_pool()
on shutdown to drain connections cleanly.
"""

from __future__ import annotations

import asyncpg

from src.core.config import get_settings

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    """Return (or lazily create) the shared asyncpg connection pool."""
    global _pool
    if _pool is None:
        cfg = get_settings()
        _pool = await asyncpg.create_pool(
            dsn=cfg.database_url,
            min_size=cfg.db_pool_min_size,
            max_size=cfg.db_pool_max_size,
            command_timeout=60,
        )
    return _pool


async def close_pool() -> None:
    """Drain and close the pool — call on application shutdown."""
    global _pool
    if _pool is not None:
        import asyncio
        try:
            await asyncio.wait_for(_pool.close(), timeout=5.0)
        except asyncio.TimeoutError:
            pass
        _pool = None


async def run_migrations() -> None:
    """Apply all schema migrations idempotently (CREATE IF NOT EXISTS)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id            UUID PRIMARY KEY,
                parent_id     UUID REFERENCES sessions(id),
                agent         TEXT NOT NULL DEFAULT 'build',
                title         TEXT,
                status        TEXT NOT NULL DEFAULT 'active',
                model         TEXT NOT NULL,
                total_tokens_in  BIGINT DEFAULT 0,
                total_tokens_out BIGINT DEFAULT 0,
                total_cost_usd   NUMERIC(12,6) DEFAULT 0,
                created_at    TIMESTAMPTZ DEFAULT NOW(),
                updated_at    TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS sessions_status ON sessions(status, updated_at DESC);

            CREATE TABLE IF NOT EXISTS messages (
                id          UUID PRIMARY KEY,
                session_id  UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                role        TEXT NOT NULL,
                parts       JSONB NOT NULL DEFAULT '[]',
                usage       JSONB,
                created_at  TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS messages_session ON messages(session_id, created_at);

            CREATE TABLE IF NOT EXISTS permission_rules (
                id          UUID PRIMARY KEY,
                scope       TEXT NOT NULL DEFAULT 'global',
                scope_id    UUID,
                permission  TEXT NOT NULL,
                pattern     TEXT NOT NULL,
                action      TEXT NOT NULL,
                created_at  TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS perm_rules_scope ON permission_rules(scope, scope_id);

            CREATE TABLE IF NOT EXISTS permission_requests (
                id            UUID PRIMARY KEY,
                session_id    UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                tool_name     TEXT NOT NULL,
                tool_input    JSONB NOT NULL DEFAULT '{}',
                permission    TEXT NOT NULL,
                patterns      TEXT[] NOT NULL DEFAULT '{}',
                status        TEXT NOT NULL DEFAULT 'pending',
                feedback      TEXT,
                created_at    TIMESTAMPTZ DEFAULT NOW(),
                responded_at  TIMESTAMPTZ
            );
            CREATE INDEX IF NOT EXISTS perm_req_pending ON permission_requests(session_id, status);

            CREATE TABLE IF NOT EXISTS organization (
                id         TEXT PRIMARY KEY,
                name       TEXT NOT NULL,
                owner_id   TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
            INSERT INTO organization (id, name, owner_id)
            VALUES ('default-org', 'Default Organization', 'admin')
            ON CONFLICT (id) DO NOTHING;

            CREATE TABLE IF NOT EXISTS server (
                server_id          TEXT PRIMARY KEY,
                name               TEXT NOT NULL,
                hostname           TEXT NOT NULL,
                system_uuid        TEXT NOT NULL UNIQUE,
                description        TEXT,
                ip_address         TEXT NOT NULL,
                public_ip_address  TEXT,
                os_name            TEXT,
                os_version         TEXT,
                enrollment_id      TEXT,
                enrolled_at        TIMESTAMP NOT NULL DEFAULT NOW(),
                enrolled_by        TEXT,
                server_status      TEXT DEFAULT 'pending',
                last_seen_at       TIMESTAMP,
                organization_id    TEXT NOT NULL REFERENCES organization(id) ON DELETE CASCADE,
                mqtt_topic         TEXT,
                mqtt_broker        TEXT,
                mqtt_port          INTEGER,
                agent_version      TEXT,
                agent_status       TEXT,
                created_at         TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at         TIMESTAMP NOT NULL DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS task_queue (
                id           SERIAL PRIMARY KEY,
                task_id      UUID DEFAULT gen_random_uuid(),
                device_id    TEXT NOT NULL REFERENCES server(server_id) ON DELETE CASCADE,
                task_type    VARCHAR(50) NOT NULL,
                payload      JSONB DEFAULT '{}',
                status       VARCHAR(20) DEFAULT 'pending',
                created_at   TIMESTAMPTZ DEFAULT NOW(),
                sent_at      TIMESTAMPTZ,
                completed_at TIMESTAMPTZ,
                result       JSONB,
                error        TEXT,
                created_by   VARCHAR(50) DEFAULT 'system'
            );

            CREATE TABLE IF NOT EXISTS projects (
                id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name        TEXT NOT NULL UNIQUE,
                description TEXT,
                created_at  TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS environments (
                id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                project_id  UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                name        TEXT NOT NULL,
                namespace   TEXT NOT NULL UNIQUE,
                server_id   TEXT REFERENCES server(server_id) ON DELETE SET NULL,
                is_default  BOOLEAN DEFAULT FALSE,
                created_at  TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(project_id, name)
            );

            CREATE TABLE IF NOT EXISTS applications (
                id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name           TEXT NOT NULL,
                environment_id UUID NOT NULL REFERENCES environments(id) ON DELETE CASCADE,
                image          TEXT,
                replicas       INT DEFAULT 1,
                status         TEXT DEFAULT 'pending',
                created_at     TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(environment_id, name)
            );

            CREATE TABLE IF NOT EXISTS k8s_resources (
                id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                application_id UUID REFERENCES applications(id) ON DELETE CASCADE,
                resource_type  TEXT NOT NULL,
                resource_name  TEXT NOT NULL,
                namespace      TEXT NOT NULL,
                manifest       JSONB,
                created_at     TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE (application_id, resource_type, resource_name)
            );

            -- Idempotent: add constraint if table existed before this column was added
            DO $$ BEGIN
                ALTER TABLE k8s_resources
                    ADD CONSTRAINT k8s_resources_app_type_name_unique
                    UNIQUE (application_id, resource_type, resource_name);
            EXCEPTION WHEN duplicate_table THEN NULL;
            END $$;

            CREATE TABLE IF NOT EXISTS install_tokens (
                token        TEXT PRIMARY KEY,
                server_name  TEXT NOT NULL,
                device_id    TEXT NOT NULL UNIQUE,
                org_id       TEXT NOT NULL DEFAULT 'default-org',
                expires_at   TIMESTAMPTZ NOT NULL,
                used_at      TIMESTAMPTZ,
                created_at   TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS task_history (
                id           SERIAL PRIMARY KEY,
                task_id      UUID NOT NULL,
                device_id    TEXT NOT NULL REFERENCES server(server_id) ON DELETE CASCADE,
                task_type    VARCHAR(50) NOT NULL,
                status       VARCHAR(20) NOT NULL,
                result       JSONB,
                error        TEXT,
                created_at   TIMESTAMPTZ,
                completed_at TIMESTAMPTZ
            );
        """)
