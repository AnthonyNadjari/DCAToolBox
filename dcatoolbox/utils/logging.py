"""Centralised logging configuration built on top of :mod:`loguru`.

A single ``logger`` instance is exported and reused across the whole code base so
that the verbosity can be controlled from one place (CLI flag, env var or call).
"""

from __future__ import annotations

import sys
from typing import Final

from loguru import logger

__all__ = ["logger", "configure_logging"]

_DEFAULT_FORMAT: Final[str] = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>"
)


def configure_logging(level: str = "INFO", *, fmt: str = _DEFAULT_FORMAT) -> None:
    """Configure the global :mod:`loguru` logger.

    Args:
        level: Minimum log level to emit (e.g. ``"DEBUG"``, ``"INFO"``).
        fmt: Loguru-compatible format string.
    """
    logger.remove()
    logger.add(sys.stderr, level=level.upper(), format=fmt, enqueue=False, backtrace=False)


# Apply a quiet, sensible default as soon as the framework is imported. Callers
# (CLI, web UI, tests) may override the level at any time.
configure_logging("INFO")
