"""
app/auth/security.py — JWT creation/verification and bcrypt password hashing.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import get_settings

_settings = get_settings()
_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ── Password hashing ──────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    """Return bcrypt hash of a plaintext password."""
    return _pwd_ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against its bcrypt hash."""
    return _pwd_ctx.verify(plain, hashed)


# ── JWT ───────────────────────────────────────────────────────────────────────

def _make_token(data: dict[str, Any], expires_delta: timedelta) -> str:
    payload = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta
    payload["exp"] = expire
    return jwt.encode(payload, _settings.jwt_secret_key, algorithm=_settings.jwt_algorithm)


def create_access_token(user_id: int, role: str) -> str:
    """Create a short-lived JWT access token."""
    return _make_token(
        {"sub": str(user_id), "role": role, "type": "access"},
        timedelta(minutes=_settings.access_token_expire_minutes),
    )


def create_refresh_token(user_id: int) -> str:
    """Create a long-lived JWT refresh token."""
    return _make_token(
        {"sub": str(user_id), "type": "refresh"},
        timedelta(days=_settings.refresh_token_expire_days),
    )


def decode_token(token: str) -> dict[str, Any]:
    """
    Decode and validate a JWT. Raises JWTError on failure.

    Returns:
        Decoded payload dict including 'sub', 'role', 'type'.
    """
    return jwt.decode(token, _settings.jwt_secret_key, algorithms=[_settings.jwt_algorithm])
