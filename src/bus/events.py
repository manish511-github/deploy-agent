"""Event schemas for the Bus + SSE system.

Every significant state change in a session publishes an Event.
Clients consume these via SSE and render them live.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class EventType(str, Enum):
    """Canonical event types emitted by the session engine."""

    TEXT_DELTA = "text_delta"
    TOOL_START = "tool_start"
    TOOL_RESULT = "tool_result"
    TOOL_ERROR = "tool_error"
    PERMISSION_ASKED = "permission_asked"
    PERMISSION_REPLIED = "permission_replied"
    STEP_START = "step_start"
    STEP_FINISH = "step_finish"
    DONE = "done"
    ERROR = "error"
    COMPACT = "compact"


class Event(BaseModel):
    """A single event on the Bus, consumed by SSE clients.

    Events are immutable, serializable, and self-describing.
    The payload shape varies by event_type; clients switch on type.
    """

    event_id: UUID = Field(default_factory=uuid4)
    event_type: EventType
    session_id: UUID
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, Any] = Field(default_factory=dict)

    def json(self) -> str:
        """Compact JSON for SSE wire format."""
        return self.model_dump_json()

    @classmethod
    def parse(cls, raw: str | dict[str, Any]) -> "Event":
        """Parse from JSON string or dict."""
        if isinstance(raw, str):
            return cls.model_validate_json(raw)
        return cls.model_validate(raw)
