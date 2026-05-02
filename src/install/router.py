"""
Agent install + enrollment endpoints.

Flow:
  1. POST /servers/register  → pre-assigns device_id, returns install command
  2. GET  /agent/install/{token} → returns ready-to-run install.sh
  3. GET  /agent/download/{arch} → serves the Go agent binary
"""

from __future__ import annotations

import os
import secrets
import textwrap
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel

from src.core.db import get_pool

router = APIRouter(tags=["install"])

# Where the Go agent binaries live inside the container
_BINARY_DIR = Path(os.environ.get("AGENT_BINARY_DIR", "/app"))
_BINARY_MAP = {
    "x86_64":  "zdeploy-agent-linux-amd64",
    "aarch64": "zdeploy-agent-linux-arm64",
    "amd64":   "zdeploy-agent-linux-amd64",
    "arm64":   "zdeploy-agent-linux-arm64",
}

# Public URL agents will call — override via env in production
def _server_url() -> str:
    return os.environ.get("PUBLIC_SERVER_URL", "http://162.19.224.95:8000")

def _mqtt_host() -> str:
    return os.environ.get("PUBLIC_MQTT_HOST", "162.19.224.95")


# ── 1. Register a new server ──────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    name: str  # user-chosen server name e.g. "my-vm"


@router.post("/servers/register")
async def register_server(body: RegisterRequest):
    """
    Pre-register a server and get back a one-time install command.

    Assigns a unique device_id and MQTT topic automatically.
    The returned curl command is valid for 24 hours.
    """
    pool = await get_pool()

    # Generate unique device_id (next integer from existing servers + tokens)
    async with pool.acquire() as conn:
        # Get max device_id across servers and pending tokens
        row = await conn.fetchrow("""
            SELECT COALESCE(MAX(id_int), 0) + 1 AS next_id FROM (
                SELECT CAST(server_id AS INTEGER) AS id_int
                FROM server
                WHERE server_id ~ '^[0-9]+$'
                UNION ALL
                SELECT CAST(device_id AS INTEGER) AS id_int
                FROM install_tokens
                WHERE device_id ~ '^[0-9]+$'
            ) ids
        """)
        device_id = str(row["next_id"])

        token = secrets.token_urlsafe(24)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=24)

        await conn.execute("""
            INSERT INTO install_tokens (token, server_name, device_id, expires_at)
            VALUES ($1, $2, $3, $4)
        """, token, body.name, device_id, expires_at)

    server_url = _server_url()
    install_cmd = f"curl -sfL {server_url}/agent/install/{token} | sudo bash"

    return {
        "server_name": body.name,
        "device_id": device_id,
        "token": token,
        "expires_at": expires_at.isoformat(),
        "install_cmd": install_cmd,
    }


# ── 2. Serve the install script ───────────────────────────────────────────────

@router.get("/agent/install/{token}", response_class=PlainTextResponse)
async def get_install_script(token: str):
    """
    Returns a ready-to-run bash script with all config baked in.
    Called by: curl -sfL .../agent/install/{token} | sudo bash
    """
    pool = await get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT token, server_name, device_id, expires_at, used_at
            FROM install_tokens WHERE token = $1
        """, token)

    if not row:
        raise HTTPException(status_code=404, detail="Invalid install token")

    if row["used_at"] is not None:
        raise HTTPException(status_code=410, detail="Install token already used")

    if datetime.now(timezone.utc) > row["expires_at"]:
        raise HTTPException(status_code=410, detail="Install token expired")

    server_url = _server_url()
    mqtt_host = _mqtt_host()
    device_id = row["device_id"]
    server_name = row["server_name"]

    script = textwrap.dedent(f"""
        #!/bin/bash
        set -e

        # DeployAI Agent Installer
        # Server: {server_name}  |  Device ID: {device_id}
        # Generated: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}

        AGENT_URL="{server_url}"
        DEVICE_ID="{device_id}"
        SERVER_NAME="{server_name}"
        MQTT_HOST="{mqtt_host}"

        echo "[deployai] Installing agent for server: $SERVER_NAME"

        # ── 1. Detect architecture ────────────────────
        ARCH=$(uname -m)
        case "$ARCH" in
            x86_64)  ARCH_SLUG="amd64" ;;
            aarch64) ARCH_SLUG="arm64" ;;
            *)
                echo "[deployai] Unsupported architecture: $ARCH"
                exit 1
                ;;
        esac
        echo "[deployai] Architecture: $ARCH ($ARCH_SLUG)"

        # ── 2. Download binary ────────────────────────
        echo "[deployai] Downloading agent binary..."
        HTTP_STATUS=$(curl -sL -w "%{{http_code}}" "$AGENT_URL/agent/download/$ARCH_SLUG" \\
            -o /usr/local/bin/zdeploy-agent)
        if [ "$HTTP_STATUS" != "200" ]; then
            echo "[deployai] ERROR: Binary download failed (HTTP $HTTP_STATUS)"
            echo "[deployai] URL: $AGENT_URL/agent/download/$ARCH_SLUG"
            rm -f /usr/local/bin/zdeploy-agent
            exit 1
        fi
        chmod +x /usr/local/bin/zdeploy-agent
        echo "[deployai] Binary installed at /usr/local/bin/zdeploy-agent"

        # ── 3. Write config ───────────────────────────
        mkdir -p /etc/zdeploy-agent
        cat > /etc/zdeploy-agent/config.yaml << CFGEOF
mqtt:
  broker_address: "$MQTT_HOST"
  broker_port: 1883
  username: ""
  password: ""
  device_id: $DEVICE_ID

mqtt_channel:
  host: "$SERVER_NAME"
  platform: 6

server_api:
  base_url: "$AGENT_URL"
  task_path: "/agent/v1/server/"
  enroll_path: "/agent/v1/enroll"
  checkin_path: "/agent/v1/checkin"

agent:
  log_level: "info"
  log_file: "/var/log/zdeploy-agent.log"
CFGEOF
        echo "[deployai] Config written to /etc/zdeploy-agent/config.yaml"

        # ── 4. Install systemd service (if available) ─
        if command -v systemctl >/dev/null 2>&1; then
            cat > /etc/systemd/system/zdeploy-agent.service << SVCEOF
[Unit]
Description=DeployAI Agent
After=network.target

[Service]
ExecStart=/usr/local/bin/zdeploy-agent -config /etc/zdeploy-agent/config.yaml
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SVCEOF
            systemctl daemon-reload
            systemctl enable zdeploy-agent
            systemctl start zdeploy-agent
            echo "[deployai] Agent started as systemd service"
            echo "[deployai] Check logs: journalctl -u zdeploy-agent -f"
        else
            # No systemd — run directly (Docker/container environments)
            echo "[deployai] No systemd found, running agent directly..."
            nohup /usr/local/bin/zdeploy-agent \\
                -config /etc/zdeploy-agent/config.yaml \\
                > /var/log/zdeploy-agent.log 2>&1 &
            echo "[deployai] Agent started (PID $!)"
            echo "[deployai] Check logs: tail -f /var/log/zdeploy-agent.log"
        fi

        echo ""
        echo "[deployai] Done! Server '$SERVER_NAME' is enrolling with DeployAI."
        echo "[deployai] It will appear in your dashboard within ~30 seconds."
    """).lstrip()

    return PlainTextResponse(content=script, media_type="text/plain")


# ── 3. Serve the binary ───────────────────────────────────────────────────────

@router.get("/agent/download/{arch}")
async def download_agent(arch: str):
    """
    Serve the Go agent binary for the requested architecture.
    arch: amd64 or arm64
    """
    filename = _BINARY_MAP.get(arch.lower())
    if not filename:
        raise HTTPException(status_code=400, detail=f"Unsupported arch: {arch}. Use amd64 or arm64.")

    path = _BINARY_DIR / filename
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Binary not found: {filename}. Run 'make build-linux' in deploy-server-agent."
        )

    return FileResponse(
        path=str(path),
        media_type="application/octet-stream",
        filename="zdeploy-agent",
    )
