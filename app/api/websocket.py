"""
app/api/websocket.py — WebSocket endpoint for voice sessions.

Handles the lifecycle of a browser ↔ VoiceLive bridge session:
  1. Accept WebSocket connection
  2. Create VoiceSession
  3. Build Semantic Kernel
  4. Instantiate VoiceLiveBridge
  5. Run the bridge (blocks until disconnect)
  6. Clean up session
"""

from __future__ import annotations

from fastapi import WebSocket, WebSocketDisconnect

from app.agent.kernel_factory import build_kernel
from app.logging_config import bind_request_id, clear_context, get_logger
from app.voice.bridge import VoiceLiveBridge
from app.voice.session_manager import SessionStatus, session_registry

logger = get_logger(__name__)


async def voice_websocket_handler(websocket: WebSocket) -> None:
    """
    Handle a single voice WebSocket session.

    Called by the FastAPI route. Manages the full session lifecycle.
    """
    await websocket.accept()

    # Create session
    session = session_registry.create(
        user_agent=websocket.headers.get("user-agent"),
        remote_ip=getattr(websocket.client, "host", None),
    )

    # Bind correlation ID for structured logs
    bind_request_id(session.session_id)

    logger.info(
        "session_started",
        session_id=session.session_id,
        remote_ip=session.remote_ip,
    )

    # Build the Semantic Kernel for this session
    kernel = build_kernel()

    # Create and run the bridge
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
        await bridge.close()
        session_registry.remove(session.session_id)
        clear_context()
        logger.info(
            "session_ended",
            session_id=session.session_id,
            turns=len(session.conversation),
            age_seconds=round(session.age_seconds, 1),
        )
