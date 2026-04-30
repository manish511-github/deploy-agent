"""
Async database pool — asyncpg-backed connection pool.

Usage:
    from src.core.db import get_pool

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT 1")

The pool is created once per process and reused. Call close_pool()
on shutdown to drain connections cleanly.
"""

from __future__ import annotations

import asyncpg

from src.core.config import get_settings

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    """Return (or lazily create) the shared asyncpg connection pool."""
    global _pool
    if _pool is None:
        cfg = get_settings()
        _pool = await asyncpg.create_pool(
            dsn=cfg.database_url,
            min_size=cfg.db_pool_min_size,
            max_size=cfg.db_pool_max_size,
            command_timeout=60,
        )
    return _pool


async def close_pool() -> None:
    """Drain and close the pool — call on application shutdown."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
