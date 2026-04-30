"""Permission service — ask/reply with asyncio.Event.

Python equivalent of OpenCode's Effect Deferred permission gate.
Blocks tool execution until the user approves, denies, or 'always-allows'.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID, uuid4

from src.bus.events import Event, EventType
from src.bus.publisher import Bus
from src.permission.ruleset import Action, evaluate, Rule, Ruleset


Reply = Literal["once", "always", "reject"]


class DeniedError(Exception):
    """Raised when a ruleset explicitly denies a tool call."""

    def __init__(self, message: str = "Permission denied by ruleset") -> None:
        super().__init__(message)


class RejectedError(Exception):
    """Raised when the user rejects a permission request."""

    def __init__(self, message: str = "Permission denied by user") -> None:
        super().__init__(message)


class CorrectedError(Exception):
    """Raised when the user rejects with feedback (redirects the AI)."""

    def __init__(self, feedback: str) -> None:
        super().__init__(f"User feedback: {feedback}")
        self.feedback = feedback


@dataclass(slots=True)
class _Request:
    """Internal pending permission request."""

    id: UUID
    session_id: UUID
    permission: str
    patterns: list[str]
    status: Literal["pending", "once", "always", "rejected"] = "pending"
    feedback: str | None = None


class PermissionService:
    """Gates tool execution through wildcard rulesets + user approval.

    Usage from inside a tool wrapper::

        result = await permission.ask(
            session_id=session_id,
            permission="exec_script",
            patterns=["apt install nginx"],
            ruleset=agent_ruleset,
        )
        if result == "rejected":
            raise RejectedError()

    The service:
    1. Evaluates each pattern against the merged ruleset.
    2. If any pattern matches ``deny`` → raises ``DeniedError`` immediately.
    3. If all patterns match ``allow`` → returns immediately.
    4. Otherwise → creates a permission request, publishes a
       ``PERMISSION_ASKED`` event, and blocks on an ``asyncio.Event``
       until ``reply()`` is called.
    """

    def __init__(self, bus: Bus) -> None:
        self._bus = bus
        self._pending: dict[UUID, _Request] = {}
        self._events: dict[UUID, asyncio.Event] = {}
        self._approved: Ruleset = []

    # ── Asking ───────────────────────────────────────────────

    async def ask(
        self,
        session_id: UUID,
        permission: str,
        patterns: list[str],
        ruleset: Ruleset,
    ) -> Literal["approved", "rejected"]:
        """Check permission. Blocks until resolved if ``ask`` is required.

        Returns:
            ``"approved"`` if allowed (either by rule or user).

        Raises:
            DeniedError: If a rule explicitly denies.
            RejectedError: If the user rejects.
            CorrectedError: If the user rejects with feedback.
        """
        needs_ask = False

        for pattern in patterns:
            rule = evaluate(permission, pattern, ruleset, self._approved)
            if rule.action == "deny":
                raise DeniedError(
                    f"Rule denies {permission}({pattern}) — matched {rule}"
                )
            if rule.action == "allow":
                continue
            needs_ask = True

        if not needs_ask:
            return "approved"

        # Publish permission_asked event and block
        request_id = uuid4()
        req = _Request(
            id=request_id,
            session_id=session_id,
            permission=permission,
            patterns=patterns,
        )
        self._pending[request_id] = req

        await self._bus.publish_event(
            Event(
                event_type=EventType.PERMISSION_ASKED,
                session_id=session_id,
                payload={
                    "request_id": str(request_id),
                    "permission": permission,
                    "patterns": patterns,
                },
            )
        )

        ev = asyncio.Event()
        self._events[request_id] = ev
        await ev.wait()

        # Resolution
        resolved = self._pending[request_id]
        if resolved.status in ("rejected",):
            if resolved.feedback:
                raise CorrectedError(resolved.feedback)
            raise RejectedError()
        return "approved"

    # ── Replying ─────────────────────────────────────────────

    async def reply(self, request_id: UUID, reply: Reply, feedback: str | None = None) -> None:
        """Resolve a pending permission request.

        Args:
            request_id: The UUID of the pending request.
            reply: ``"once"``, ``"always"``, or ``"reject"``.
            feedback: Optional user message on rejection (triggers ``CorrectedError``).
        """
        req = self._pending.get(request_id)
        if req is None:
            return

        req.status = reply if reply != "reject" else "rejected"
        if feedback:
            req.feedback = feedback

        # Wake the blocked ask()
        ev = self._events.pop(request_id, None)
        if ev is not None:
            ev.set()

        if reply == "always":
            # Add session-scoped allow rules
            for pattern in req.patterns:
                self._approved.append(
                    Rule(permission=req.permission, pattern=pattern, action="allow")
                )
            # Re-evaluate other pending requests in same session
            await self._reevaluate_session(req.session_id)

        await self._bus.publish_event(
            Event(
                event_type=EventType.PERMISSION_REPLIED,
                session_id=req.session_id,
                payload={
                    "request_id": str(request_id),
                    "reply": reply,
                },
            )
        )

    # ── Internal ─────────────────────────────────────────────

    async def _reevaluate_session(self, session_id: UUID) -> None:
        """After an 'always' reply, check if other pending requests now auto-allow."""
        for rid, req in list(self._pending.items()):
            if req.session_id != session_id:
                continue
            if req.status != "pending":
                continue
            ok = all(
                evaluate(req.permission, pat, self._approved).action == "allow"
                for pat in req.patterns
            )
            if ok:
                req.status = "always"
                ev = self._events.pop(rid, None)
                if ev is not None:
                    ev.set()
