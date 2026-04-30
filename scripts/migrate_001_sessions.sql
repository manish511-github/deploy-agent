-- Migration 001: Add sessions, messages, permission_rules, permission_requests
-- Run once against the target database:
--   psql $DATABASE_URL -f scripts/migrate_001_sessions.sql

BEGIN;

-- ── Sessions ────────────────────────────────────────────────────────────────
-- Tracks each agent chat session (top-level or spawned as a subagent).
CREATE TABLE IF NOT EXISTS sessions (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_id        UUID REFERENCES sessions(id) ON DELETE SET NULL,
    agent            TEXT NOT NULL DEFAULT 'default',
    title            TEXT,
    status           TEXT NOT NULL DEFAULT 'active'
                         CHECK (status IN ('active', 'completed', 'failed', 'cancelled')),
    model            TEXT NOT NULL,
    total_tokens_in  BIGINT NOT NULL DEFAULT 0,
    total_tokens_out BIGINT NOT NULL DEFAULT 0,
    total_cost_usd   NUMERIC(12, 6) NOT NULL DEFAULT 0,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS sessions_parent_id_idx ON sessions (parent_id);
CREATE INDEX IF NOT EXISTS sessions_status_idx    ON sessions (status);

-- ── Messages ─────────────────────────────────────────────────────────────────
-- Each turn in a session (user, assistant, tool).
CREATE TABLE IF NOT EXISTS messages (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role       TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'tool')),
    parts      JSONB NOT NULL DEFAULT '[]',
    usage      JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS messages_session_id_idx ON messages (session_id);

-- ── Permission Rules ─────────────────────────────────────────────────────────
-- Declarative allow/deny/ask ruleset matched against tool call patterns.
-- scope='global' applies to all sessions; scope='session' scopes to one session.
CREATE TABLE IF NOT EXISTS permission_rules (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scope      TEXT NOT NULL DEFAULT 'global' CHECK (scope IN ('global', 'session')),
    scope_id   UUID,        -- session id when scope='session', NULL for global
    permission TEXT NOT NULL CHECK (permission IN ('allow', 'deny', 'ask')),
    pattern    TEXT NOT NULL,   -- glob pattern matched against tool name, e.g. "exec.*"
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS permission_rules_scope_idx ON permission_rules (scope, scope_id);

-- ── Permission Requests ──────────────────────────────────────────────────────
-- Runtime requests for human approval when a tool call matches an 'ask' rule.
CREATE TABLE IF NOT EXISTS permission_requests (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id   UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    tool_name    TEXT NOT NULL,
    tool_input   JSONB NOT NULL DEFAULT '{}',
    permission   TEXT NOT NULL,
    patterns     TEXT[] NOT NULL DEFAULT '{}',
    status       TEXT NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending', 'approved', 'denied')),
    feedback     TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    responded_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS permission_requests_session_idx ON permission_requests (session_id);
CREATE INDEX IF NOT EXISTS permission_requests_status_idx  ON permission_requests (status);

COMMIT;
