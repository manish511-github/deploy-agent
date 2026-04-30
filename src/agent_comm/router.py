from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from typing import Any, Dict

from src.agent_comm.models import CheckinRequest, TaskResponse
from src.agent_comm.service import AgentService

router = APIRouter(prefix="/agent/v1", tags=["agent"])

def get_agent_service() -> AgentService:
    return AgentService()

@router.post("/server/{device_id}", response_model=Dict[str, Any])
async def handle_server_checkin(
    device_id: str, 
    request: CheckinRequest,
    service: AgentService = Depends(get_agent_service)
):
    """
    Endpoint for Go agent to check in or report task results.
    Replacing the Django linux.py -> linux_server() view.
    """
    # 1. Agent is idle, asking for work
    if request.status == "idle":
        task = service.get_next_pending_task(device_id)
        if task:
            service.mark_task_sent(task.task_id)
            return TaskResponse(
                task_id=str(task.task_id),
                task_type=task.task_type,
                payload=task.payload
            ).model_dump()
        return {} # No pending tasks
        
    # 2. Agent reporting successful task completion
    elif request.status in ("success", "acknowledged"):
        if not request.task_id:
            raise HTTPException(status_code=400, detail="task_id is required for success status")
            
        service.complete_task(
            task_id=request.task_id,
            status="success",
            result=request.data
        )
        
        # Check if there's another task waiting immediately
        task = service.get_next_pending_task(device_id)
        if task:
            service.mark_task_sent(task.task_id)
            return TaskResponse(
                task_id=str(task.task_id),
                task_type=task.task_type,
                payload=task.payload
            ).model_dump()
        return {}

    # 3. Agent reporting task failure
    elif request.status in ("error", "failure"):
        if not request.task_id:
            raise HTTPException(status_code=400, detail="task_id is required for error status")
            
        service.complete_task(
            task_id=request.task_id,
            status="failed",
            error=request.error or "Unknown error"
        )
        return {}
        
    else:
        raise HTTPException(status_code=400, detail=f"Unknown status: {request.status}")

@router.post("/enroll")
async def enroll_device(data: Dict[str, Any]):
    """
    Placeholder for initial device enrollment.
    """
    # TODO: Implement enrollment logic
    return {"status": "Enrolled", "deviceId": "test-device-id"}

@router.post("/checkin")
async def checkin_device(data: Dict[str, Any]):
    """
    Placeholder for periodic checkins.
    """
    # TODO: Implement checkin logic
    return {}
