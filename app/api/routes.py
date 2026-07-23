"""
app/api/routes.py — HTTP routes for the Sainsbury's Voice Agent.

Routes:
  GET  /                          → Serve the UI (index.html)
  GET  /login                     → Login page
  GET  /register                  → Registration page
  GET  /dashboard                 → User dashboard
  GET  /admin                     → Admin dashboard
  GET  /health                    → Health check (DB + config)
  GET  /api/v1/products           → Product search REST endpoint
  GET  /api/v1/offers             → Current offers REST endpoint
  GET  /api/v1/stores             → Store list REST endpoint
  GET  /api/v1/sessions           → Session stats (admin)

  POST /api/v1/auth/register      → Register new user
  POST /api/v1/auth/login         → Login → JWT tokens
  POST /api/v1/auth/logout        → Logout (client-side token drop)
  POST /api/v1/auth/refresh       → Refresh access token
  GET  /api/v1/auth/me            → Current user profile

  GET  /api/v1/conversations      → List user's sessions
  POST /api/v1/conversations      → Create new session
  GET  /api/v1/conversations/{id} → Get session messages
  PATCH /api/v1/conversations/{id}→ Rename session
  DELETE /api/v1/conversations/{id}→ Delete session

  GET  /api/v1/admin/stats        → Dashboard metrics (admin)
  GET  /api/v1/admin/users        → List all users (admin)
  GET  /api/v1/admin/users/{id}   → User detail + history (admin)
  PATCH /api/v1/admin/users/{id}/status → Enable/disable user (admin)
  DELETE /api/v1/admin/users/{id} → Delete user (admin)
"""

from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse

from app.auth.dependencies import get_current_user, require_admin
from app.auth.schemas import LoginRequest, RefreshRequest, RegisterRequest, UserUpdateStatus
from app.auth import service as auth_svc
from app.conversation import service as conv_svc
from app.config import get_settings
from app.database.connection import fetchall, fetchone
from app.logging_config import get_logger
from app.voice.session_manager import session_registry

logger = get_logger(__name__)
_settings = get_settings()

router = APIRouter()

_START_TIME = time.time()


# ── UI Pages ───────────────────────────────────────────────────────────────────

@router.get("/", include_in_schema=False)
async def serve_ui() -> FileResponse:
    """Serve the main voice UI."""
    return FileResponse("app/static/index.html")


@router.get("/login", include_in_schema=False)
async def serve_login() -> FileResponse:
    return FileResponse("app/static/login.html")


@router.get("/register", include_in_schema=False)
async def serve_register() -> FileResponse:
    return FileResponse("app/static/register.html")


@router.get("/dashboard", include_in_schema=False)
async def serve_dashboard() -> FileResponse:
    return FileResponse("app/static/dashboard.html")


@router.get("/admin", include_in_schema=False)
async def serve_admin() -> FileResponse:
    return FileResponse("app/static/admin.html")


# ── Health ─────────────────────────────────────────────────────────────────────

@router.get("/health", tags=["ops"])
async def health_check() -> JSONResponse:
    """Liveness + readiness check. Returns 200 if healthy, 503 if not."""
    checks: dict = {}
    healthy = True

    # Database check
    try:
        row = await fetchone("SELECT COUNT(*) AS cnt FROM products", ())
        checks["database"] = {"status": "ok", "products": row["cnt"] if row else 0}
    except Exception as exc:
        checks["database"] = {"status": "error", "message": str(exc)}
        healthy = False

    # Config check
    checks["config"] = {
        "status": "ok",
        "endpoint_configured": bool(_settings.azure_openai_endpoint),
        "key_configured": bool(_settings.azure_openai_api_key),
    }

    # Session stats
    checks["sessions"] = {"active": session_registry.active_count}

    # Uptime
    checks["uptime_seconds"] = round(time.time() - _START_TIME, 1)

    status_code = 200 if healthy else 503
    return JSONResponse(
        content={
            "status": "healthy" if healthy else "degraded",
            "checks": checks,
        },
        status_code=status_code,
    )


# ── Products ───────────────────────────────────────────────────────────────────

@router.get("/api/v1/products", tags=["retail"])
async def search_products(
    q: str = Query("", description="Search term"),
    category: str = Query("", description="Category filter"),
    on_offer: bool = Query(False, description="Only show items on offer"),
    limit: int = Query(20, ge=1, le=50),
) -> JSONResponse:
    """Search the product catalogue."""
    conditions = ["1=1"]
    params: list = []

    if q:
        conditions.append("(name LIKE ? OR description LIKE ? OR subcategory LIKE ?)")
        params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])

    if category:
        conditions.append("category = ?")
        params.append(category)

    if on_offer:
        conditions.append("on_offer = 1")

    where = " AND ".join(conditions)
    rows = await fetchall(
        f"""SELECT id, name, category, subcategory, price, unit,
                   on_offer, offer_price, in_stock, nectar_points
            FROM products WHERE {where}
            ORDER BY on_offer DESC, category, name
            LIMIT ?""",
        tuple(params + [limit]),
    )

    return JSONResponse({"count": len(rows), "products": rows})


# ── Offers ─────────────────────────────────────────────────────────────────────

@router.get("/api/v1/offers", tags=["retail"])
async def get_offers(
    category: str = Query("", description="Category filter"),
    nectar_only: bool = Query(False, description="Only Nectar deals"),
) -> JSONResponse:
    """Get current active offers."""
    conditions = ["(valid_until >= date('now') OR valid_until IS NULL)"]
    params: list = []

    if category:
        conditions.append("category LIKE ?")
        params.append(f"%{category}%")

    if nectar_only:
        conditions.append("is_nectar_deal = 1")

    where = " AND ".join(conditions)
    rows = await fetchall(
        f"""SELECT id, title, description, category, offer_type,
                   discount_pct, valid_until, is_nectar_deal, nectar_points_bonus
            FROM offers WHERE {where}
            ORDER BY is_nectar_deal DESC, discount_pct DESC""",
        tuple(params),
    )

    return JSONResponse({"count": len(rows), "offers": rows})


# ── Stores ─────────────────────────────────────────────────────────────────────

@router.get("/api/v1/stores", tags=["retail"])
async def get_stores(
    city: str = Query("", description="Filter by city"),
) -> JSONResponse:
    """Get store list with opening hours."""
    if city:
        rows = await fetchall(
            "SELECT id, name, address, city, postcode, phone, monday_hours, tuesday_hours, wednesday_hours, thursday_hours, friday_hours, saturday_hours, sunday_hours, has_cafe, has_pharmacy, has_click_collect, parking_spaces FROM stores WHERE city LIKE ?",
            (f"%{city}%",),
        )
    else:
        rows = await fetchall(
            "SELECT id, name, address, city, postcode, phone, monday_hours, tuesday_hours, wednesday_hours, thursday_hours, friday_hours, saturday_hours, sunday_hours, has_cafe, has_pharmacy, has_click_collect, parking_spaces FROM stores ORDER BY city",
            (),
        )
    return JSONResponse({"count": len(rows), "stores": rows})


# ── Admin sessions ─────────────────────────────────────────────────────────────

@router.get("/api/v1/sessions", tags=["ops"])
async def get_session_stats() -> JSONResponse:
    """Return active session statistics."""
    return JSONResponse(session_registry.stats())


# ── Auth ───────────────────────────────────────────────────────────────────────

@router.post("/api/v1/auth/register", tags=["auth"])
async def register(req: RegisterRequest) -> JSONResponse:
    """Register a new user account."""
    user = await auth_svc.register_user(req)
    from app.auth.security import create_access_token, create_refresh_token
    access = create_access_token(user["id"], user["role"])
    refresh = create_refresh_token(user["id"])
    return JSONResponse({
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "user": auth_svc._user_out(user),
    }, status_code=201)


@router.post("/api/v1/auth/login", tags=["auth"])
async def login(req: LoginRequest) -> JSONResponse:
    """Authenticate and return JWT tokens."""
    result = await auth_svc.login_user(req)
    return JSONResponse(result)


@router.post("/api/v1/auth/logout", tags=["auth"])
async def logout() -> JSONResponse:
    """Logout — client should discard stored tokens."""
    return JSONResponse({"message": "Logged out successfully"})


@router.post("/api/v1/auth/refresh", tags=["auth"])
async def refresh_token(req: RefreshRequest) -> JSONResponse:
    """Issue new access + refresh tokens from a valid refresh token."""
    result = await auth_svc.refresh_tokens(req.refresh_token)
    return JSONResponse(result)


@router.get("/api/v1/auth/me", tags=["auth"])
async def me(user: dict = Depends(get_current_user)) -> JSONResponse:
    """Return the current authenticated user's profile."""
    return JSONResponse(auth_svc._user_out(user))


# ── Conversations ──────────────────────────────────────────────────────────────

@router.get("/api/v1/conversations", tags=["conversations"])
async def list_conversations(
    search: str = Query("", description="Search by title"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
) -> JSONResponse:
    """List the current user's conversation sessions."""
    sessions = await conv_svc.get_sessions(user["id"], search=search, skip=skip, limit=limit)
    return JSONResponse({"count": len(sessions), "sessions": sessions})


@router.post("/api/v1/conversations", tags=["conversations"])
async def create_conversation(
    user: dict = Depends(get_current_user),
) -> JSONResponse:
    """Manually create a new conversation session."""
    session_id = await conv_svc.create_session(user["id"])
    return JSONResponse({"session_id": session_id}, status_code=201)


@router.get("/api/v1/conversations/{session_id}", tags=["conversations"])
async def get_conversation(
    session_id: int,
    user: dict = Depends(get_current_user),
) -> JSONResponse:
    """Get messages for a specific conversation session."""
    messages = await conv_svc.get_session_messages(session_id, user["id"])
    return JSONResponse({"session_id": session_id, "messages": messages})


@router.patch("/api/v1/conversations/{session_id}", tags=["conversations"])
async def rename_conversation(
    session_id: int,
    body: dict,
    user: dict = Depends(get_current_user),
) -> JSONResponse:
    """Rename a conversation session."""
    new_title = body.get("title", "").strip()
    if not new_title:
        raise HTTPException(status_code=400, detail="Title cannot be empty")
    await conv_svc.rename_session(session_id, user["id"], new_title)
    return JSONResponse({"message": "Renamed successfully"})


@router.delete("/api/v1/conversations/{session_id}", tags=["conversations"])
async def delete_conversation(
    session_id: int,
    user: dict = Depends(get_current_user),
) -> JSONResponse:
    """Delete a conversation session and all its messages."""
    await conv_svc.delete_session(session_id, user["id"])
    return JSONResponse({"message": "Deleted successfully"})


# ── Admin ──────────────────────────────────────────────────────────────────────

@router.get("/api/v1/admin/stats", tags=["admin"])
async def admin_stats(admin: dict = Depends(require_admin)) -> JSONResponse:
    """Return aggregate dashboard statistics."""
    stats = await conv_svc.get_admin_stats()
    stats["active_voice_sessions"] = session_registry.active_count
    return JSONResponse(stats)


@router.get("/api/v1/admin/users", tags=["admin"])
async def admin_list_users(
    search: str = Query("", description="Search by name or email"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    admin: dict = Depends(require_admin),
) -> JSONResponse:
    """List all users (admin only)."""
    users = await auth_svc.list_users(skip=skip, limit=limit, search=search)
    safe = [auth_svc._user_out(u) for u in users]
    return JSONResponse({"count": len(safe), "users": safe})


@router.get("/api/v1/admin/users/{user_id}", tags=["admin"])
async def admin_user_detail(
    user_id: int,
    admin: dict = Depends(require_admin),
) -> JSONResponse:
    """Get user detail including their conversation history (admin only)."""
    user = await auth_svc.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    conversations = await conv_svc.get_admin_user_conversations(user_id)
    return JSONResponse({
        "user": auth_svc._user_out(user),
        "conversations": conversations,
    })


@router.patch("/api/v1/admin/users/{user_id}/status", tags=["admin"])
async def admin_update_user_status(
    user_id: int,
    body: UserUpdateStatus,
    admin: dict = Depends(require_admin),
) -> JSONResponse:
    """Enable or disable a user account (admin only)."""
    await auth_svc.update_user_status(user_id, body.is_active)
    status_str = "enabled" if body.is_active else "disabled"
    return JSONResponse({"message": f"User {status_str} successfully"})


@router.delete("/api/v1/admin/users/{user_id}", tags=["admin"])
async def admin_delete_user(
    user_id: int,
    admin: dict = Depends(require_admin),
) -> JSONResponse:
    """Permanently delete a user and all their data (admin only)."""
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    await auth_svc.delete_user(user_id)
    return JSONResponse({"message": "User deleted successfully"})
