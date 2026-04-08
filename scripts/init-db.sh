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

    -- Sample server for testing
    -- Sample server for testing uses the actual internal docker IP pattern
    INSERT INTO server (server_id, name, hostname, system_uuid, ip_address, os_name, os_version, server_status, organization_id, mqtt_topic)
    VALUES ('srv-001', 'prod-server', 'prod-server', 'uuid-prod-001', '172.20.0.4', 'Ubuntu', '22.04', 'active', 'default-org', 'servers/default-org/srv-001')
    ON CONFLICT (server_id) DO UPDATE SET ip_address = '172.20.0.4';
EOSQL

echo "✅ Database schema initialized!"
