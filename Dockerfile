# ============================================
# DeployAI Phase 2 — Multi-stage Docker build
# ============================================
# Supports both "server" mode (FastAPI + SSE) and "cli" mode (Typer + Rich).
#
# Build:
#   docker build -t deploy-ai .
#
# Run server:
#   docker run -p 8000:8000 --env-file .env deploy-ai server
#
# Run CLI (interactive):
#   docker run -it --env-file .env deploy-ai chat
#
# Run CLI (one-shot):
#   docker run --env-file .env deploy-ai run "list all servers"
#
# ──────────────────────────────────────────────

# --- Stage 1: Builder ---
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies (gcc for asyncpg, libpq for psycopg2)
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Copy project metadata
COPY pyproject.toml ./
COPY src/ ./src/

# Install into a virtual env
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e "."


# --- Stage 2: Runtime ---
FROM python:3.12-slim AS runtime

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq5 openssh-client curl && \
    rm -rf /var/lib/apt/lists/*

# Copy virtual env from builder (includes uvicorn, asyncpg, sse-starlette, etc.)
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application source (for mounted volume overrides in dev)
COPY src/ ./src/

# Copy Go agent binaries (served via /agent/download/{arch})
COPY zdeploy-agent-linux-amd64 ./zdeploy-agent-linux-amd64
COPY zdeploy-agent-linux-arm64 ./zdeploy-agent-linux-arm64

# Create SSH directory for key mounting
RUN mkdir -p /root/.ssh && chmod 700 /root/.ssh

# Default environment
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app

# Healthcheck for server mode
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Entrypoint is the CLI binary
ENTRYPOINT ["deploy-ai"]

# Default command: show help
CMD ["--help"]
