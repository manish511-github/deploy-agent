from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

class CheckinRequest(BaseModel):
    """Payload sent by the Go agent on wake-up or task completion."""
    status: str
    task_id: Optional[str] = None
    task_type: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

class TaskResponse(BaseModel):
    """Payload sent from the server back to the Go agent."""
    task_id: str
    task_type: str
    payload: Dict[str, Any] = Field(default_factory=dict)
