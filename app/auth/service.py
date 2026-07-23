"""
app/auth/service.py — Business logic for user authentication and management.
"""

from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, status
from jose import JWTError

from app.auth.schemas import LoginRequest, RegisterRequest
from app.auth.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.database.connection import execute, fetchall, fetchone
from app.logging_config import get_logger

logger = get_logger(__name__)


# ── Registration ──────────────────────────────────────────────────────────────

async def register_user(req: RegisterRequest) -> dict:
    """Create a new user. Raises 409 if email already registered."""
    existing = await fetchone("SELECT id FROM users WHERE email = ?", (req.email.lower(),))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    pw_hash = hash_password(req.password)
    user_id = await execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        (req.name.strip(), req.email.lower(), pw_hash),
    )

    user = await fetchone("SELECT * FROM users WHERE id = ?", (user_id,))
    logger.info("user_registered", user_id=user_id, email=req.email)
    return user


# ── Login ─────────────────────────────────────────────────────────────────────

async def login_user(req: LoginRequest) -> dict:
    """
    Authenticate credentials. Returns dict with tokens + user.
    Raises 401 on invalid credentials or disabled account.
    """
    user = await fetchone("SELECT * FROM users WHERE email = ?", (req.email.lower(),))
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    if not user["is_active"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    # Update last_login
    await execute(
        "UPDATE users SET last_login = datetime('now') WHERE id = ?",
        (user["id"],),
    )

    access = create_access_token(user["id"], user["role"])
    refresh = create_refresh_token(user["id"])

    logger.info("user_login", user_id=user["id"])
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "user": _user_out(user),
    }


# ── Refresh ───────────────────────────────────────────────────────────────────

async def refresh_tokens(refresh_token: str) -> dict:
    """Issue new access + refresh tokens from a valid refresh token."""
    try:
        payload = decode_token(refresh_token)
        if payload.get("type") != "refresh":
            raise JWTError("not a refresh token")
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user = await fetchone("SELECT * FROM users WHERE id = ? AND is_active = 1", (user_id,))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return {
        "access_token": create_access_token(user["id"], user["role"]),
        "refresh_token": create_refresh_token(user["id"]),
        "token_type": "bearer",
        "user": _user_out(user),
    }


# ── User management ───────────────────────────────────────────────────────────

async def get_user_by_id(user_id: int) -> Optional[dict]:
    return await fetchone("SELECT * FROM users WHERE id = ?", (user_id,))


async def list_users(skip: int = 0, limit: int = 50, search: str = "") -> list[dict]:
    if search:
        return await fetchall(
            "SELECT * FROM users WHERE name LIKE ? OR email LIKE ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (f"%{search}%", f"%{search}%", limit, skip),
        )
    return await fetchall(
        "SELECT * FROM users ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (limit, skip),
    )


async def update_user_status(user_id: int, is_active: bool) -> bool:
    rows = await execute(
        "UPDATE users SET is_active = ? WHERE id = ?",
        (1 if is_active else 0, user_id),
    )
    return True


async def reset_user_password(user_id: int, new_password: str) -> bool:
    pw_hash = hash_password(new_password)
    await execute("UPDATE users SET password_hash = ? WHERE id = ?", (pw_hash, user_id))
    return True


async def delete_user(user_id: int) -> bool:
    await execute("DELETE FROM users WHERE id = ?", (user_id,))
    logger.info("user_deleted", user_id=user_id)
    return True


# ── Internal helpers ──────────────────────────────────────────────────────────

def _user_out(user: dict) -> dict:
    """Strip sensitive fields from a user row."""
    return {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "role": user["role"],
        "is_active": bool(user["is_active"]),
        "created_at": user["created_at"],
        "last_login": user.get("last_login"),
    }
