"""
app/auth/dependencies.py — FastAPI dependency injectors for auth.

Usage:
    @router.get("/me")
    async def me(user=Depends(get_current_user)):
        ...

    @router.get("/admin-only")
    async def admin(user=Depends(require_admin)):
        ...
"""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError

from app.auth.security import decode_token
from app.database.connection import fetchone

_bearer = HTTPBearer(auto_error=False)


async def _resolve_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    token: Optional[str] = Query(None, description="JWT token (for WebSocket clients)"),
) -> Optional[str]:
    """Extract JWT from Authorization header or ?token= query param."""
    if credentials:
        return credentials.credentials
    return token


async def get_current_user(raw_token: Optional[str] = Depends(_resolve_token)) -> dict:
    """
    Decode JWT and return the matching user row.
    Raises HTTP 401 if token is missing or invalid.
    """
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_token(raw_token)
        if payload.get("type") != "access":
            raise JWTError("wrong token type")
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await fetchone("SELECT * FROM users WHERE id = ?", (user_id,))
    if not user or not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or disabled",
        )
    return user


async def get_optional_user(
    raw_token: Optional[str] = Depends(_resolve_token),
) -> Optional[dict]:
    """Like get_current_user but returns None instead of raising 401."""
    if not raw_token:
        return None
    try:
        payload = decode_token(raw_token)
        if payload.get("type") != "access":
            return None
        user_id = int(payload["sub"])
        user = await fetchone("SELECT * FROM users WHERE id = ? AND is_active = 1", (user_id,))
        return user
    except Exception:
        return None


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """Enforce admin role. Raises HTTP 403 for regular users."""
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user
