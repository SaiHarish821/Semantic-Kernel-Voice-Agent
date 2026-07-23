"""
app/config.py — Centralised application configuration via Pydantic Settings.

All values are loaded from environment variables / .env file.
A single validated Settings instance is cached via lru_cache.
"""

from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-wide settings loaded from .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Azure OpenAI / Realtime ─────────────────────────────────────────────
    azure_openai_endpoint: str
    azure_openai_api_key: str
    azure_openai_realtime_deployment: str = "gpt-realtime"
    azure_openai_api_version: str = "2025-04-01-preview"
    azure_openai_chat_deployment: str = "gpt-5"

    # ── Application ─────────────────────────────────────────────────────────
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_log_level: str = "INFO"

    # ── Database ────────────────────────────────────────────────────────────
    database_path: str = "./data/sainsburys.db"

    # ── Voice ───────────────────────────────────────────────────────────────
    voice_name: str = "alloy"
    audio_format: str = "pcm16"
    audio_sample_rate: int = 24000

    # ── Store ───────────────────────────────────────────────────────────────
    default_store_id: str = "ST001"

    # ── Session ─────────────────────────────────────────────────────────────
    max_context_turns: int = 6
    session_timeout_seconds: int = 300

    # ── CORS ─────────────────────────────────────────────────────────────────
    cors_origins: str = "http://localhost:8000,http://127.0.0.1:8000"

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def realtime_websocket_url(self) -> str:
        """Azure OpenAI Realtime WebSocket endpoint."""
        from urllib.parse import urlparse

        endpoint = self.azure_openai_endpoint.strip()
        parsed = urlparse(endpoint)
        scheme = "wss" if parsed.scheme in ("https", "wss") else "ws"
        netloc = parsed.netloc or parsed.path.split("/")[0]

        deployment = self.azure_openai_realtime_deployment
        api_version = self.azure_openai_api_version
        return (
            f"{scheme}://{netloc}/openai/realtime"
            f"?deployment={deployment}&api-version={api_version}"
        )

    @field_validator("app_log_level")
    @classmethod
    def _validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in valid:
            raise ValueError(f"app_log_level must be one of {valid}")
        return upper


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached Settings singleton."""
    return Settings()
