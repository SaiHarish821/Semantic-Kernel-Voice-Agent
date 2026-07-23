"""
run.py — Entry point for the Sainsbury's AI Voice Agent.

Usage:
    python run.py                       # Development
    python run.py --env production      # Production (no reload)
"""

import argparse
import sys

import uvicorn

from app.config import get_settings
from app.logging_config import configure_logging


def main() -> None:
    parser = argparse.ArgumentParser(description="Sainsbury's AI Voice Agent")
    parser.add_argument(
        "--env",
        choices=["development", "production"],
        default=None,
        help="Override APP_ENV from .env",
    )
    parser.add_argument("--host", default=None, help="Override APP_HOST")
    parser.add_argument("--port", type=int, default=None, help="Override APP_PORT")
    args = parser.parse_args()

    settings = get_settings()

    # CLI overrides take precedence
    if args.env:
        settings.app_env = args.env
    if args.host:
        settings.app_host = args.host
    if args.port:
        settings.app_port = args.port

    configure_logging(settings.app_log_level)

    is_dev = settings.app_env == "development"

    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=is_dev,
        log_level=settings.app_log_level.lower(),
        access_log=is_dev,
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
