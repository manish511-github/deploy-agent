# DeployAI Phase 2 — Docker Quick Reference

## Architecture

```
┌─────────┐      ┌──────────┐      ┌──────────┐      ┌──────────┐
│   CLI   │ ───▶ │  Server  │ ───▶ │ Postgres │      │   MQTT   │
│ (typer) │      │(FastAPI) │      │(Bus+DB)  │      │(Go agent)│
│         │ ◀─── │          │      └──────────┘      └──────────┘
│  Rich   │ SSE  │  /events │
│  Live   │      │  /messages
└─────────┘      └──────────┘
```

## Quick Start

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env with your GEMINI_API_KEY
```

### 2. Start infrastructure + server

```bash
docker-compose up -d server postgres mqtt redis
```

Wait a few seconds for Postgres to init.

### 3. Verify server is up

```bash
curl http://localhost:8000/health
curl http://localhost:8000/docs   # FastAPI Swagger UI
```

### 4. Interactive chat (server mode)

```bash
docker-compose run -it --rm cli
```

### 5. One-shot command

```bash
docker-compose run -it --rm cli run "list all servers"
```

### 6. Direct mode (no server)

```bash
docker-compose run -it --rm cli chat --direct
```

## Services

| Service | What | Port | Access |
|---------|------|------|--------|
| `server` | FastAPI + SSE | 8000 | `http://localhost:8000` |
| `cli` | Typer + Rich | — | `docker-compose run -it --rm cli` |
| `postgres` | Sessions + messages | 5432 | localhost (dev) |
| `mqtt` | Go agent wake | 1883 | Internal |
| `mcp` | MCP server | 8811 | `http://localhost:8811` |

## Useful Commands

```bash
# View logs
docker-compose logs -f server
docker-compose logs -f cli

# Restart server
docker-compose restart server

# Stop everything
docker-compose down

# Stop and delete data
docker-compose down -v

# Rebuild after code changes
docker-compose build --no-cache server
docker-compose up -d server

# Run with .env file explicitly
docker-compose --env-file .env up -d

# Shell into running server
docker-compose exec server bash

# Check DB schema
docker-compose exec postgres psql -U deployai -d deployai -c "\dt"
```

## Development (Hot Reload)

Both `server` and `cli` mount `./src:/app/src` for live code changes.

Edit any `.py` file → changes reflect immediately (FastAPI `--reload` for server, re-run for CLI).

## Production Notes

- Remove `--reload` from server command
- Remove volume mounts (`./src:/app/src`)
- Set `PYTHONDONTWRITEBYTECODE=0`
- Use a proper WSGI/ASGI server (Gunicorn + Uvicorn workers)
- Add TLS termination (Traefik / Nginx / Caddy)
- Use external Postgres (RDS, Cloud SQL)
- Use managed MQTT (HiveMQ, AWS IoT)

## Troubleshooting

**"Connection refused" from CLI:**
- Server might not be ready. Check `docker-compose logs server`
- Verify `SERVER_BASE_URL` in `.env` or docker-compose env

**"database does not exist":**
- Postgres init script needs to re-run. `docker-compose down -v` then `up -d`

**"Permission denied" on SSH key:**
- `chmod 600 test_ssh_key`

**SSE not streaming:**
- Check `curl -N http://localhost:8000/sessions/{id}/events`
- Verify session was created first: `POST /sessions`
