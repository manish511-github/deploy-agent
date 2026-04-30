#!/bin/sh
# Initialize database schema for deploy-agent
# This runs automatically when PostgreSQL container starts for the first time

set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Organization table
    CREATE TABLE IF NOT EXISTS organization (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        owner_id TEXT NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
    );

    -- Server table
    CREATE TABLE IF NOT EXISTS server (
        server_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        hostname TEXT NOT NULL,
        system_uuid TEXT NOT NULL UNIQUE,
        description TEXT,
        ip_address TEXT NOT NULL,
        public_ip_address TEXT,
        os_name TEXT,
        os_version TEXT,
        enrollment_id TEXT,
        enrolled_at TIMESTAMP NOT NULL DEFAULT NOW(),
        enrolled_by TEXT,
        server_status TEXT DEFAULT 'pending',
        last_seen_at TIMESTAMP,
        organization_id TEXT NOT NULL REFERENCES organization(id) ON DELETE CASCADE,
        mqtt_topic TEXT,
        mqtt_broker TEXT,
        mqtt_port INTEGER,
        agent_version TEXT,
        agent_status TEXT,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
    );

    -- Default organization
    INSERT INTO organization (id, name, owner_id)
    VALUES ('default-org', 'Default Organization', 'admin')
    ON CONFLICT (id) DO NOTHING;

    -- Task Queue table for Agent Commands
    CREATE TABLE IF NOT EXISTS task_queue (
        id            SERIAL PRIMARY KEY,
        task_id       UUID DEFAULT gen_random_uuid(),
        device_id     TEXT NOT NULL REFERENCES server(server_id) ON DELETE CASCADE,
        task_type     VARCHAR(50) NOT NULL,
        payload       JSONB DEFAULT '{}',
        status        VARCHAR(20) DEFAULT 'pending',
        created_at    TIMESTAMPTZ DEFAULT NOW(),
        sent_at       TIMESTAMPTZ,
        completed_at  TIMESTAMPTZ,
        result        JSONB,
        error         TEXT,
        created_by    VARCHAR(50) DEFAULT 'system'
    );

    -- Task History table
    CREATE TABLE IF NOT EXISTS task_history (
        id            SERIAL PRIMARY KEY,
        task_id       UUID NOT NULL,
        device_id     TEXT NOT NULL REFERENCES server(server_id) ON DELETE CASCADE,
        task_type     VARCHAR(50) NOT NULL,
        status        VARCHAR(20) NOT NULL,
        result        JSONB,
        error         TEXT,
        created_at    TIMESTAMPTZ,
        completed_at  TIMESTAMPTZ
    );

    -- Sample server for testing
    -- Sample server for testing uses the actual internal docker IP pattern
    INSERT INTO server (server_id, name, hostname, system_uuid, ip_address, os_name, os_version, server_status, organization_id, mqtt_topic)
    VALUES ('1', 'test-server', 'test-server', 'uuid-prod-001', '172.20.0.4', 'Ubuntu', '22.04', 'active', 'default-org', 'zdeploy/test-server/6/1')
    ON CONFLICT (server_id) DO UPDATE SET ip_address = '172.20.0.4';

    -- ───────────────────────────────────────────
    -- Phase 2 Tables: Sessions, Messages, Permissions
    -- ───────────────────────────────────────────

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

EOSQL

echo "✅ Database schema initialized!"
