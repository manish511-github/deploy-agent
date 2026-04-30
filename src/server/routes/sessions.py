"""Session REST + SSE routes.

POST /sessions              → create session
POST /sessions/:id/messages → submit prompt (spawns engine)
GET  /sessions/:id/events   → SSE stream
POST /sessions/:id/resume   → resume after restart
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from src.bus.events import Event
from src.bus.publisher import Bus
from src.core.db import get_pool
from src.session.engine import SessionEngine
from src.session.store import SessionStore
from src.permission.service import PermissionService


router = APIRouter(prefix="/sessions", tags=["sessions"])


# ── Request/Response models ───────────────────────────────


class CreateSessionRequest(BaseModel):
    agent: str = "build"
    model: str = "gemini-2.5-flash-lite"
    title: str | None = None


class CreateSessionResponse(BaseModel):
    id: str
    agent: str
    created_at: str


class PostMessageRequest(BaseModel):
    content: str


class PostMessageResponse(BaseModel):
    message_id: str
    status: str = "accepted"


# ── Dependencies ──────────────────────────────────────────


async def _get_store() -> SessionStore:
    pool = await get_pool()
    return SessionStore(pool)


async def _get_bus() -> Bus:
    pool = await get_pool()
    return Bus(pool)


async def _get_engine() -> SessionEngine:
    pool = await get_pool()
    bus = Bus(pool)
    store = SessionStore(pool)
    permission = PermissionService(bus)
    return SessionEngine(bus, store, permission)


# ── Routes ────────────────────────────────────────────────


@router.post("", response_model=CreateSessionResponse)
async def create_session(req: CreateSessionRequest) -> CreateSessionResponse:
    store = await _get_store()
    session = await store.create_session(
        agent=req.agent,
        model=req.model,
        title=req.title,
    )
    return CreateSessionResponse(
        id=str(session.id),
        agent=session.agent,
        created_at=session.created_at.isoformat(),
    )


@router.post("/{session_id}/messages", response_model=PostMessageResponse)
async def post_message(session_id: str, req: PostMessageRequest) -> PostMessageResponse:
    engine = await _get_engine()
    sid = UUID(session_id)

    # Spawn the engine as a background task so we can return 202 immediately.
    # Wrap in _run_engine() so exceptions are logged instead of silently dropped.
    async def _run_engine() -> None:
        try:
            await engine.stream(
                session_id=sid,
                user_message=req.content,
            )
        except Exception:
            import logging
            logging.getLogger("deployai.api").exception("Engine task failed for session %s", sid)

    asyncio.create_task(_run_engine())

    return PostMessageResponse(
        message_id="",  # Could generate one if needed
        status="accepted",
    )


@router.get("/{session_id}/events")
async def get_events(session_id: str, request: Request) -> EventSourceResponse:
    """SSE endpoint: stream all events for a session.

    Clients (CLI, web, Slack) connect here and render events live.
    """
    bus = await _get_bus()
    sid = UUID(session_id)

    async def event_generator():
        try:
            async for event in bus.subscribe_session(session_id):
                if await request.is_disconnected():
                    break
                yield {"data": event.json()}
        except Exception:
            # Client disconnected or other error — clean exit
            pass

    return EventSourceResponse(event_generator())


@router.post("/{session_id}/resume")
async def resume_session(session_id: str) -> dict[str, str]:
    """Resume a session after server restart.

    Loads the latest checkpoint and re-runs the engine from where it left off.
    For Phase 2 this is a no-op placeholder; full resume logic in Phase 3.
    """
    return {"status": "resumed", "session_id": session_id}
