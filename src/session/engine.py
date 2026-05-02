"""Session streaming engine.

The core async generator that runs a LangGraph session, translates
stream events into Bus events, and handles permission gating inside
tool wrappers.

Pattern derived from:
- Claude Code's query.ts (hand-rolled streaming loop)
- OpenCode's session/processor.ts (stream consumer → DB updates)
"""

from __future__ import annotations

import asyncio
import logging
import traceback
import warnings
from typing import Any
from uuid import UUID

from langchain_core.messages import HumanMessage
from langchain_core.tools import BaseTool
from pydantic import Field, ConfigDict

from src.bus.events import Event, EventType
from src.bus.publisher import Bus
from src.permission.ruleset import Ruleset
from src.permission.service import PermissionService
from src.session.store import SessionStore
from src.graph.graph import build_graph

logger = logging.getLogger("deployai.engine")

# LangGraph's MemorySaver warns when serialising AIMessage.parsed set by
# with_structured_output (DeploymentPlan / ReviewResult). Harmless noise.
warnings.filterwarnings("ignore", message=".*PydanticSerializationUnexpectedValue.*")


class PermissionToolWrapper(BaseTool):
    """Wraps a LangChain tool with permission gating.

    Inherits from ``BaseTool`` so LangGraph's ``ToolNode`` accepts it
    directly. When the LLM calls the tool, we first check the ruleset.
    If ``ask`` is required, we block on the PermissionService until
    the user replies via the CLI/web.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # Tool metadata delegated from the wrapped tool
    name: str = ""
    description: str = ""

    # Internal fields — excluded from serialization
    wrapped: Any = Field(exclude=True, default=None)
    ruleset: Any = Field(exclude=True, default=None)
    permission: Any = Field(exclude=True, default=None)
    session_id: Any = Field(exclude=True, default=None)

    def __init__(self, wrapped: Any, ruleset: Any, permission: Any, session_id: UUID) -> None:
        super().__init__(
            name=wrapped.name,
            description=wrapped.description,
            args_schema=getattr(wrapped, "args_schema", None),
            wrapped=wrapped,
            ruleset=ruleset,
            permission=permission,
            session_id=session_id,
        )

    def _extract_patterns(self, args: dict[str, Any]) -> list[str]:
        """Derive permission patterns from tool arguments."""
        patterns: list[str] = []
        if "script" in args:
            patterns.append(args["script"])
        if "task_type" in args:
            patterns.append(args["task_type"])
        if "risk_level" in args:
            patterns.append(f"risk={args['risk_level']}")
        if not patterns:
            patterns.append("*")
        return patterns

    def _run(self, **kwargs: Any) -> str:
        """Sync fallback — should not be called in async contexts."""
        return asyncio.run(self._arun(**kwargs))

    async def _arun(self, **kwargs: Any) -> str:
        """Async entry point called by LangGraph's ToolNode."""
        patterns = self._extract_patterns(kwargs)
        try:
            await self.permission.ask(
                session_id=self.session_id,
                permission=self.wrapped.name,
                patterns=patterns,
                ruleset=self.ruleset,
            )
        except Exception as exc:
            logger.warning("Permission denied for %s: %s", self.wrapped.name, exc)
            return f"Permission denied: {exc}"

        # Pass empty callbacks so the inner tool's ainvoke() does NOT fire
        # a second set of on_tool_start/on_tool_end events. The outer
        # PermissionToolWrapper invocation already emits those via LangGraph's
        # ToolNode — without this, every tool result appears twice in the UI.
        return await self.wrapped.ainvoke(kwargs, config={"callbacks": []})


class SessionEngine:
    """Runs LangGraph sessions and publishes events to the Bus."""

    def __init__(
        self,
        bus: Bus,
        store: SessionStore,
        permission: PermissionService,
    ) -> None:
        self.bus = bus
        self.store = store
        self.permission = permission

    async def stream(
        self,
        session_id: UUID,
        user_message: str,
        agent: str = "build",
        model: str = "gemini-2.5-flash-lite",
    ) -> None:
        """Run one turn of a session and publish all events to the Bus.

        This function does not return data — it side-effects the Bus
        and the database. Clients consume events via SSE.
        """
        logger.info("[session %s] Starting stream for: %s", session_id, user_message)

        # Publish STEP_START so CLI knows we're alive
        await self.bus.publish_event(
            Event(
                event_type=EventType.STEP_START,
                session_id=session_id,
                payload={"message": "Thinking..."},
            )
        )

        # 1. Persist user message
        await self.store.add_message(
            session_id=session_id,
            role="user",
            parts=[{"type": "text", "text": user_message}],
        )

        # 2. Load agent ruleset (hardcoded minimal for Phase 2)
        ruleset = self._load_ruleset(agent)

        # 3. Build tools with permission wrappers
        from src.tools import ALL_TOOLS
        wrapped_tools = [
            PermissionToolWrapper(t, ruleset, self.permission, session_id)
            for t in ALL_TOOLS
        ]
        logger.info("[session %s] Tools: %s", session_id, [t.name for t in wrapped_tools])

        # 4. Build graph (no interrupt_before — permission is in tool wrapper)
        graph = build_graph(tools=wrapped_tools)

        # 5. Run graph with astream_events
        config = {"configurable": {"thread_id": str(session_id)}}
        inputs = {"messages": [HumanMessage(content=user_message)]}

        text_buffer = ""
        event_count = 0
        current_node: str | None = None

        try:
            async for event in graph.astream_events(inputs, config, version="v2"):
                event_count += 1
                kind = event.get("event")
                data = event.get("data", {})
                name = event.get("name", "")
                metadata = event.get("metadata", {})

                logger.debug(
                    "[session %s] Event: %s | name=%s",
                    session_id,
                    kind,
                    name,
                )

                # Stream ALL text deltas (planner & reviewer disabled).
                if kind == "on_chat_model_stream":
                    chunk = data.get("chunk")
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        token = str(chunk.content)
                        text_buffer += token
                        await self.bus.publish_event(
                            Event(
                                event_type=EventType.TEXT_DELTA,
                                session_id=session_id,
                                payload={"text": token},
                            )
                        )

                elif kind == "on_tool_start":
                    # Only emit for the top-level PermissionToolWrapper invocation.
                    # The inner tool is now called via _arun (not ainvoke), so it
                    # does NOT fire its own on_tool_start/on_tool_end events.
                    if metadata.get("langgraph_node") == "tools":
                        await self.bus.publish_event(
                            Event(
                                event_type=EventType.TOOL_START,
                                session_id=session_id,
                                payload={"tool": name},
                            )
                        )

                elif kind == "on_tool_end":
                    if metadata.get("langgraph_node") == "tools":
                        output = data.get("output", "")
                        # LangGraph ToolNode returns a ToolMessage object.
                        # Extract its .content field for human-readable display.
                        if hasattr(output, "content"):
                            result_text = str(output.content)
                        else:
                            result_text = str(output)
                        await self.bus.publish_event(
                            Event(
                                event_type=EventType.TOOL_RESULT,
                                session_id=session_id,
                                payload={"tool": name, "result": result_text[:2000]},
                            )
                        )

            logger.info(
                "[session %s] Stream complete. Events: %d, Executor text: %d chars",
                session_id,
                event_count,
                len(text_buffer),
            )

            # 6. Send DONE event
            await self.bus.publish_event(
                Event(
                    event_type=EventType.DONE,
                    session_id=session_id,
                    payload={},
                )
            )

            # 7. Persist assistant response (executor's streamed text is canonical)
            if text_buffer:
                await self.store.add_message(
                    session_id=session_id,
                    role="assistant",
                    parts=[{"type": "text", "text": text_buffer}],
                )

        except Exception as exc:
            tb = traceback.format_exc()
            logger.exception("[session %s] Engine error", session_id)
            error_msg = str(exc) or type(exc).__name__
            await self.bus.publish_event(
                Event(
                    event_type=EventType.ERROR,
                    session_id=session_id,
                    payload={"error": f"{error_msg}\n\n{tb}"},
                )
            )

    def _load_ruleset(self, agent: str) -> Ruleset:
        """Hardcoded minimal ruleset for Phase 2.

        Phase 3 will load from agent definitions + user config.
        """
        from src.permission.ruleset import Rule
        return [
            Rule(permission="execute_dynamic_script", pattern="risk=high", action="ask"),
            Rule(permission="execute_dynamic_script", pattern="risk=medium", action="ask"),
            Rule(permission="send_agent_task", pattern="device.restart", action="ask"),
            Rule(permission="send_agent_task", pattern="device.shutdown", action="ask"),
            Rule(permission="send_agent_task", pattern="device.wipe", action="ask"),
            Rule(permission="*", pattern="*", action="allow"),
        ]
