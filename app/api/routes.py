"""
app/api/routes.py — HTTP routes for the Sainsbury's Voice Agent.

Routes:
  GET  /                      → Serve the UI (index.html)
  GET  /health                → Health check (DB + config)
  GET  /api/v1/products       → Product search REST endpoint
  GET  /api/v1/offers         → Current offers REST endpoint
  GET  /api/v1/stores         → Store list REST endpoint
  GET  /api/v1/sessions       → Session stats (admin)
"""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse

from app.config import get_settings
from app.database.connection import fetchall, fetchone
from app.logging_config import get_logger
from app.voice.session_manager import session_registry

logger = get_logger(__name__)
_settings = get_settings()

router = APIRouter()

_START_TIME = time.time()


# ── UI ─────────────────────────────────────────────────────────────────────────

@router.get("/", include_in_schema=False)
async def serve_ui() -> FileResponse:
    """Serve the main UI."""
    return FileResponse("app/static/index.html")


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
            "SELECT id, name, address, city, postcode, phone, monday_hours, sunday_hours FROM stores WHERE city LIKE ?",
            (f"%{city}%",),
        )
    else:
        rows = await fetchall(
            "SELECT id, name, address, city, postcode, phone, monday_hours, sunday_hours FROM stores ORDER BY city",
            (),
        )
    return JSONResponse({"count": len(rows), "stores": rows})


# ── Admin ──────────────────────────────────────────────────────────────────────

@router.get("/api/v1/sessions", tags=["ops"])
async def get_session_stats() -> JSONResponse:
    """Return active session statistics."""
    return JSONResponse(session_registry.stats())
