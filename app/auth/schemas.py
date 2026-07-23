"""
app/auth/schemas.py — Pydantic request/response schemas for authentication.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: "UserOut"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    role: str
    is_active: bool
    created_at: str
    last_login: Optional[str] = None


class UserUpdateStatus(BaseModel):
    is_active: bool


class PasswordResetRequest(BaseModel):
    new_password: str = Field(..., min_length=8)
