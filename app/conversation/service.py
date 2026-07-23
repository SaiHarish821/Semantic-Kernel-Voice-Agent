"""
app/conversation/service.py — Conversation session and message persistence.

Each authenticated voice session maps to one conversation_session row.
Every transcript turn (user speech or assistant response) becomes a
conversation_message row.  All queries use the existing DB helpers.
"""

from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, status

from app.database.connection import execute, fetchall, fetchone
from app.logging_config import get_logger

logger = get_logger(__name__)


# ── Session lifecycle ─────────────────────────────────────────────────────────

async def create_session(user_id: int, title: str = "Voice Conversation") -> int:
    """Create a new conversation session and return its ID."""
    session_id = await execute(
        "INSERT INTO conversation_sessions (user_id, title) VALUES (?, ?)",
        (user_id, title),
    )
    logger.info("conversation_session_created", session_id=session_id, user_id=user_id)
    return session_id


async def add_message(
    session_id: int,
    role: str,
    content: str,
    latency_ms: int = 0,
) -> int:
    """Append a message to a session and increment its counter."""
    msg_id = await execute(
        "INSERT INTO conversation_messages (session_id, role, content, latency_ms) VALUES (?, ?, ?, ?)",
        (session_id, role, content, latency_ms),
    )
    await execute(
        """UPDATE conversation_sessions
           SET message_count = message_count + 1,
               updated_at = datetime('now')
           WHERE id = ?""",
        (session_id,),
    )
    return msg_id


async def finalize_session(
    session_id: int,
    duration_seconds: float = 0,
    token_usage: int = 0,
) -> None:
    """Update duration and token usage when the voice session ends."""
    await execute(
        """UPDATE conversation_sessions
           SET duration_seconds = ?, token_usage = ?, updated_at = datetime('now')
           WHERE id = ?""",
        (round(duration_seconds, 1), token_usage, session_id),
    )

    # Auto-generate title from first user message if still default
    sess = await fetchone(
        "SELECT title FROM conversation_sessions WHERE id = ?", (session_id,)
    )
    if sess and sess["title"] == "Voice Conversation":
        first_msg = await fetchone(
            "SELECT content FROM conversation_messages WHERE session_id = ? AND role = 'user' ORDER BY id LIMIT 1",
            (session_id,),
        )
        if first_msg:
            short = first_msg["content"][:60].strip()
            if len(first_msg["content"]) > 60:
                short += "…"
            await execute(
                "UPDATE conversation_sessions SET title = ? WHERE id = ?",
                (short, session_id),
            )

    logger.info("conversation_session_finalized", session_id=session_id, duration=duration_seconds)


# ── CRUD ──────────────────────────────────────────────────────────────────────

async def get_sessions(
    user_id: int,
    search: str = "",
    skip: int = 0,
    limit: int = 20,
) -> list[dict]:
    """Return a user's conversation sessions, newest first. Optionally search by title."""
    if search:
        return await fetchall(
            """SELECT id, title, created_at, updated_at, message_count, duration_seconds
               FROM conversation_sessions
               WHERE user_id = ? AND title LIKE ?
               ORDER BY updated_at DESC LIMIT ? OFFSET ?""",
            (user_id, f"%{search}%", limit, skip),
        )
    return await fetchall(
        """SELECT id, title, created_at, updated_at, message_count, duration_seconds
           FROM conversation_sessions
           WHERE user_id = ?
           ORDER BY updated_at DESC LIMIT ? OFFSET ?""",
        (user_id, limit, skip),
    )


async def get_session_messages(session_id: int, user_id: int) -> list[dict]:
    """Return messages for a session, enforcing ownership."""
    sess = await fetchone(
        "SELECT user_id FROM conversation_sessions WHERE id = ?", (session_id,)
    )
    if not sess:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if sess["user_id"] != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    return await fetchall(
        "SELECT id, role, content, timestamp, latency_ms FROM conversation_messages WHERE session_id = ? ORDER BY id",
        (session_id,),
    )


async def rename_session(session_id: int, user_id: int, new_title: str) -> bool:
    """Rename a session (ownership enforced)."""
    sess = await fetchone(
        "SELECT user_id FROM conversation_sessions WHERE id = ?", (session_id,)
    )
    if not sess:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if sess["user_id"] != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    await execute(
        "UPDATE conversation_sessions SET title = ?, updated_at = datetime('now') WHERE id = ?",
        (new_title.strip()[:200], session_id),
    )
    return True


async def delete_session(session_id: int, user_id: int) -> bool:
    """Delete a session and its messages (cascades via FK)."""
    sess = await fetchone(
        "SELECT user_id FROM conversation_sessions WHERE id = ?", (session_id,)
    )
    if not sess:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if sess["user_id"] != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    await execute("DELETE FROM conversation_sessions WHERE id = ?", (session_id,))
    logger.info("conversation_session_deleted", session_id=session_id, user_id=user_id)
    return True


# ── Admin analytics ───────────────────────────────────────────────────────────

async def get_admin_stats() -> dict:
    """Aggregate metrics for the admin dashboard."""
    total_users = await fetchone("SELECT COUNT(*) AS cnt FROM users", ())
    active_users = await fetchone("SELECT COUNT(*) AS cnt FROM users WHERE is_active = 1", ())
    total_sessions = await fetchone("SELECT COUNT(*) AS cnt FROM conversation_sessions", ())
    total_messages = await fetchone("SELECT COUNT(*) AS cnt FROM conversation_messages", ())
    avg_latency = await fetchone(
        "SELECT AVG(latency_ms) AS avg FROM conversation_messages WHERE latency_ms > 0", ()
    )
    total_tokens = await fetchone(
        "SELECT SUM(token_usage) AS total FROM conversation_sessions", ()
    )
    today_sessions = await fetchone(
        "SELECT COUNT(*) AS cnt FROM conversation_sessions WHERE date(created_at) = date('now')", ()
    )

    return {
        "total_users": total_users["cnt"] if total_users else 0,
        "active_users": active_users["cnt"] if active_users else 0,
        "total_sessions": total_sessions["cnt"] if total_sessions else 0,
        "total_messages": total_messages["cnt"] if total_messages else 0,
        "avg_latency_ms": round(avg_latency["avg"] or 0, 1) if avg_latency else 0,
        "total_token_usage": total_tokens["total"] or 0 if total_tokens else 0,
        "sessions_today": today_sessions["cnt"] if today_sessions else 0,
    }


async def get_admin_user_conversations(user_id: int) -> list[dict]:
    """Get all conversation sessions for a specific user (admin use)."""
    return await fetchall(
        """SELECT id, title, created_at, updated_at, message_count, duration_seconds, token_usage
           FROM conversation_sessions WHERE user_id = ? ORDER BY updated_at DESC""",
        (user_id,),
    )
