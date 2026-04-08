# ============================================
# DeployAI — Multi-stage Docker build
# ============================================

# --- Stage 1: Builder ---
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml ./
COPY src/ ./src/

# Install dependencies into a virtual env
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .


# --- Stage 2: Runtime ---
FROM python:3.12-slim AS runtime

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq5 openssh-client && \
    rm -rf /var/lib/apt/lists/*

# Copy virtual env from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application source
COPY src/ ./src/

# Create SSH directory for key mounting
RUN mkdir -p /root/.ssh && chmod 700 /root/.ssh

# Default environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Entry point — default to interactive chat
ENTRYPOINT ["deploy-ai"]
CMD ["chat"]
