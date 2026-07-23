"""
app/api/websocket.py — WebSocket endpoint for voice sessions.

Handles the lifecycle of a browser ↔ VoiceLive bridge session:
  1. Accept WebSocket connection
  2. Extract optional JWT from ?token= query param
  3. Create VoiceSession (with user_id if authenticated)
  4. Create conversation DB session for authenticated users
  5. Build Semantic Kernel
  6. Instantiate VoiceLiveBridge
  7. Run the bridge (blocks until disconnect)
  8. Finalize conversation DB session
  9. Clean up session
"""

from __future__ import annotations

from fastapi import WebSocket, WebSocketDisconnect

from app.agent.kernel_factory import build_kernel
from app.auth.dependencies import get_optional_user
from app.auth.security import decode_token
from app.conversation import service as conv_svc
from app.logging_config import bind_request_id, clear_context, get_logger
from app.voice.bridge import VoiceLiveBridge
from app.voice.session_manager import SessionStatus, session_registry

logger = get_logger(__name__)


async def voice_websocket_handler(websocket: WebSocket, token: str | None = None) -> None:
    """
    Handle a single voice WebSocket session.

    Called by the FastAPI route. Manages the full session lifecycle,
    including optional conversation persistence for authenticated users.
    """
    await websocket.accept()

    # ── Resolve authenticated user (optional) ─────────────────────────────────
    user_id: int | None = None
    if token:
        try:
            payload = decode_token(token)
            if payload.get("type") == "access":
                user_id = int(payload["sub"])
        except Exception:
            pass  # Anonymous session — voice still works

    # ── Create in-memory session ──────────────────────────────────────────────
    session = session_registry.create(
        user_agent=websocket.headers.get("user-agent"),
        remote_ip=getattr(websocket.client, "host", None),
        user_id=user_id,
    )

    # Bind correlation ID for structured logs
    bind_request_id(session.session_id)

    logger.info(
        "session_started",
        session_id=session.session_id,
        remote_ip=session.remote_ip,
        authenticated=user_id is not None,
    )

    # ── Create conversation DB session for authenticated users ────────────────
    if user_id:
        try:
            db_session_id = await conv_svc.create_session(user_id=user_id)
            session.db_session_id = db_session_id
        except Exception as exc:
            logger.warning("conv_session_create_failed", error=str(exc))

    # ── Build kernel and bridge ───────────────────────────────────────────────
    kernel = build_kernel()
    bridge = VoiceLiveBridge(
        browser_ws=websocket,
        session=session,
        kernel=kernel,
    )

    try:
        await bridge.run()
    except WebSocketDisconnect:
        logger.info("client_disconnected", session_id=session.session_id)
    except Exception as exc:
        logger.error(
            "session_error",
            session_id=session.session_id,
            error=str(exc),
        )
        session.status = SessionStatus.ERROR
    finally:
        # ── Finalize conversation DB session ──────────────────────────────────
        if session.db_session_id:
            try:
                await conv_svc.finalize_session(
                    session_id=session.db_session_id,
                    duration_seconds=session.age_seconds,
                )
            except Exception as exc:
                logger.warning("conv_session_finalize_failed", error=str(exc))

        await bridge.close()
        session_registry.remove(session.session_id)
        clear_context()
        logger.info(
            "session_ended",
            session_id=session.session_id,
            turns=len(session.conversation),
            age_seconds=round(session.age_seconds, 1),
            authenticated=user_id is not None,
        )
