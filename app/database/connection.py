"""
app/database/connection.py — Async SQLite connection management.

Provides:
  - init_db(): create tables + seed data on startup
  - get_db(): async context manager yielding an aiosqlite Connection
  - close_db(): graceful shutdown
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import aiosqlite

from app.config import get_settings
from app.logging_config import get_logger

logger = get_logger(__name__)

_settings = get_settings()

# ── Lifecycle helpers ───────────────────────────────────────────────────────


async def init_db() -> None:
    """Create database directory, apply schema, and seed sample data."""
    db_path = _settings.database_path
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

    from app.database.models import CREATE_TABLES_SQL
    from app.database.seed import seed_all

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.executescript(CREATE_TABLES_SQL)
        await db.commit()
        await seed_all(db)

    logger.info("database_ready", path=db_path)


async def close_db() -> None:
    """No persistent pool to close with aiosqlite — placeholder for future."""
    logger.info("database_closed")


# ── Per-request connection ──────────────────────────────────────────────────


@asynccontextmanager
async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """Yield a short-lived aiosqlite connection with Row factory."""
    async with aiosqlite.connect(_settings.database_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")
        yield db


async def fetchall(sql: str, params: tuple = ()) -> list[dict]:
    """Execute a SELECT and return all rows as plain dicts."""
    async with get_db() as db:
        async with db.execute(sql, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def fetchone(sql: str, params: tuple = ()) -> dict | None:
    """Execute a SELECT and return the first row as a plain dict, or None."""
    async with get_db() as db:
        async with db.execute(sql, params) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def execute(sql: str, params: tuple = ()) -> int:
    """Execute an INSERT/UPDATE/DELETE and return lastrowid."""
    async with get_db() as db:
        cursor = await db.execute(sql, params)
        await db.commit()
        return cursor.lastrowid or 0
