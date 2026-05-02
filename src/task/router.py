import logging
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.task.models import CheckinRequest, TaskResponse
from src.task.service import TaskService
from src.fleet.repository import PostgresServerRepository
from src.infrastructure.project_repo import PostgresProjectRepository
from src.core.db import get_pool

logger = logging.getLogger("deployai.enroll")

router = APIRouter(prefix="/agent/v1", tags=["agent"])


class EnrollRequest(BaseModel):
    device_id: str
    hostname: str
    os: str
    os_version: str = ""
    cpu_cores: int = 0
    ram_gb: int = 0
    ip_address: str = ""
    arch: str = ""
    agent_version: str = ""
    k3s_version: str = ""


def _provision_defaults(server_id: str, hostname: str) -> str:
    """
    Idempotently create default project + production environment for a server.
    Returns the default namespace string.
    """
    namespace = "default-production"
    project_repo = PostgresProjectRepository()

    project = project_repo.get_or_create_project(
        name="default",
        description="Default project",
    )
    project_repo.get_or_create_environment(
        project_id=str(project.id),
        name="production",
        namespace=namespace,
        server_id=server_id,
        is_default=True,
    )
    return namespace


def get_task_service() -> TaskService:
    return TaskService()


@router.post("/server/{device_id}", response_model=Dict[str, Any])
async def handle_server_checkin(
    device_id: str,
    request: CheckinRequest,
    service: TaskService = Depends(get_task_service),
):
    """Endpoint for Go agent to check in or report task results."""
    if request.status == "idle":
        task = service.get_next_pending_task(device_id)
        if task:
            service.mark_task_sent(task.task_id)
            return TaskResponse(
                task_id=str(task.task_id),
                task_type=task.task_type,
                payload=task.payload,
            ).model_dump()
        return {}

    elif request.status in ("success", "acknowledged"):
        if not request.task_id:
            raise HTTPException(status_code=400, detail="task_id is required for success status")
        service.complete_task(task_id=request.task_id, status="success", result=request.data)
        task = service.get_next_pending_task(device_id)
        if task:
            service.mark_task_sent(task.task_id)
            return TaskResponse(
                task_id=str(task.task_id),
                task_type=task.task_type,
                payload=task.payload,
            ).model_dump()
        return {}

    elif request.status in ("error", "failure"):
        if not request.task_id:
            raise HTTPException(status_code=400, detail="task_id is required for error status")
        service.complete_task(
            task_id=request.task_id,
            status="failed",
            error=request.error or "Unknown error",
        )
        return {}

    else:
        raise HTTPException(status_code=400, detail=f"Unknown status: {request.status}")


@router.post("/enroll")
async def enroll_device(data: EnrollRequest):
    """
    Called by the Go agent on first startup.

    1. Upsert server record in DB
    2. Build and persist MQTT topic
    3. Auto-create default project + production environment
    4. Mark install token as used
    5. Return connection details to the agent
    """
    logger.info("Enrollment request from device_id=%s hostname=%s", data.device_id, data.hostname)

    # 1. Upsert server record
    fleet_repo = PostgresServerRepository()
    server = fleet_repo.upsert_server(
        device_id=data.device_id,
        hostname=data.hostname,
        ip_address=data.ip_address,
        os_name=data.os,
        os_version=data.os_version,
        agent_version=data.agent_version,
        k3s_version=data.k3s_version,
    )

    # 2. Build MQTT topic and persist it (using simple device-based topic)
    mqtt_topic = f"zdeploy/device/{data.device_id}"
    fleet_repo.update_mqtt_topic(server.server_id, mqtt_topic)

    # 3. Auto-create default project + production environment
    default_namespace = _provision_defaults(server.server_id, data.hostname)

    # 4. Mark install token as used (idempotent — ignore if token not found)
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE install_tokens SET used_at = $1 WHERE device_id = $2 AND used_at IS NULL",
                datetime.now(timezone.utc),
                data.device_id,
            )
    except Exception:
        pass  # Non-fatal — token tracking is best-effort

    logger.info(
        "Enrolled server_id=%s mqtt_topic=%s namespace=%s",
        server.server_id, mqtt_topic, default_namespace,
    )

    return {
        "server_id": server.server_id,
        "mqtt_topic": mqtt_topic,
        "default_namespace": default_namespace,
        "status": "enrolled",
    }


@router.post("/checkin")
async def checkin_device(data: Dict[str, Any]):
    return {}
