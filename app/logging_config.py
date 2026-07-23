"""
app/logging_config.py — Structured JSON logging with structlog.

Provides:
  - configure_logging(): call once at startup
  - get_logger(name): returns a bound structlog logger
  - bind_request_id(): binds a correlation ID to the current context
"""

from __future__ import annotations

import logging
import sys
import uuid

import structlog


def configure_logging(log_level: str = "INFO") -> None:
    """Configure structlog + stdlib logging. Call once at application startup."""

    # Stdlib root logger → structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper(), logging.INFO),
    )

    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]

    structlog.configure(
        processors=shared_processors
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(),
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Suppress noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a named structlog logger."""
    return structlog.get_logger(name)


def bind_request_id(request_id: str | None = None) -> str:
    """Bind a correlation/request ID to the current structlog context."""
    rid = request_id or str(uuid.uuid4())
    structlog.contextvars.bind_contextvars(request_id=rid)
    return rid


def clear_context() -> None:
    """Clear structlog context variables (call at end of request)."""
    structlog.contextvars.clear_contextvars()
