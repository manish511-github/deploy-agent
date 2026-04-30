"""Permission reply route.

POST /permissions/:id/reply  → approve / deny / always-allow
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel

from src.bus.publisher import Bus
from src.core.db import get_pool
from src.permission.service import PermissionService


router = APIRouter(prefix="/permissions", tags=["permissions"])


class PermissionReplyRequest(BaseModel):
    reply: str  # "once" | "always" | "reject"
    message: str | None = None  # optional feedback on rejection


async def _get_permission() -> PermissionService:
    pool = await get_pool()
    bus = Bus(pool)
    return PermissionService(bus)


@router.post("/{request_id}/reply")
async def reply_to_permission(request_id: str, req: PermissionReplyRequest) -> dict[str, str]:
    """User approves or denies a permission request.

    Triggers the awaiting asyncio.Event in PermissionService.ask().
    """
    permission = await _get_permission()
    await permission.reply(
        request_id=UUID(request_id),
        reply=req.reply,  # type: ignore[arg-type]
        feedback=req.message,
    )
    return {"status": "ok", "request_id": request_id}
