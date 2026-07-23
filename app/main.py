"""
app/main.py — FastAPI application factory with lifespan management.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.api.websocket import voice_websocket_handler
from app.config import get_settings
from app.database.connection import close_db, init_db
from app.logging_config import configure_logging, get_logger

_settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown."""
    configure_logging(_settings.app_log_level)
    logger = get_logger(__name__)
    logger.info(
        "startup",
        env=_settings.app_env,
        host=_settings.app_host,
        port=_settings.app_port,
    )
    await init_db()
    yield
    await close_db()
    logger.info("shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Sainsbury's AI Voice Agent",
        description="Real-time AI voice assistant for Sainsbury's retail operations",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs" if not _settings.is_production else None,
        redoc_url=None,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Static files (UI)
    app.mount("/static", StaticFiles(directory="app/static"), name="static")

    # HTTP routes
    app.include_router(router)

    # WebSocket voice endpoint
    @app.websocket("/ws/voice")
    async def ws_voice(websocket: WebSocket) -> None:
        await voice_websocket_handler(websocket)

    return app


app = create_app()
