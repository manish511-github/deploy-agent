"""Postgres LISTEN/NOTIFY event bus.

Thin wrapper around asyncpg's notification support.
Zero additional infrastructure — Postgres is already there.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncIterator

import asyncpg

from src.bus.events import Event

logger = logging.getLogger("deployai.bus")


class Bus:
    """Publishes and subscribes to events via Postgres NOTIFY/LISTEN.

    Each session gets its own channel: ``session_<uuid>``.
    Permission requests also get a dedicated channel:
    ``perm_request_<uuid>`` so the engine can block on a reply.
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    # ── Publishing ───────────────────────────────────────────

    async def publish(self, channel: str, payload: Event | dict) -> None:
        """NOTIFY a channel with a JSON payload."""
        data = payload.json() if isinstance(payload, Event) else json.dumps(payload)
        async with self._pool.acquire() as conn:
            await conn.execute("SELECT pg_notify($1, $2)", channel, data)

    async def publish_event(self, event: Event) -> None:
        """Publish to the canonical session channel."""
        await self.publish(f"session_{event.session_id}", event)

    # ── Subscribing ──────────────────────────────────────────

    async def subscribe(self, channel: str) -> AsyncIterator[Event]:
        """LISTEN on a channel and yield Events as they arrive.

        Holds a dedicated connection for the lifetime of the subscription.
        Cancel the async iterator to release the connection.
        """
        conn: asyncpg.Connection | None = None
        queue: asyncio.Queue[str] = asyncio.Queue()

        def _on_notify(
            connection: asyncpg.Connection,
            pid: int,
            channel: str,
            payload: str,
        ) -> None:
            queue.put_nowait(payload)

        try:
            conn = await self._pool.acquire()
            await conn.add_listener(channel, _on_notify)
            logger.debug("Subscribed to channel: %s", channel)

            while True:
                try:
                    payload = await queue.get()
                    yield Event.parse(payload)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.warning("Malformed notification payload", exc_info=True)
                    continue

        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Bus subscriber error on channel %s", channel)
            raise
        finally:
            if conn is not None:
                try:
                    await conn.remove_listener(channel, _on_notify)
                except Exception:
                    pass
                await self._pool.release(conn)
                logger.debug("Released subscription connection for %s", channel)

    async def subscribe_session(self, session_id: str) -> AsyncIterator[Event]:
        """Convenience: subscribe to ``session_<id>``."""
        async for ev in self.subscribe(f"session_{session_id}"):
            yield ev
