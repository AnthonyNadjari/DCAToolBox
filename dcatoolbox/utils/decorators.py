"""Small, reusable function decorators."""

from __future__ import annotations

import functools
import time
from collections.abc import Callable
from typing import Any, TypeVar

from dcatoolbox.utils.logging import logger

__all__ = ["timed"]

_F = TypeVar("_F", bound=Callable[..., Any])


def timed(func: _F) -> _F:
    """Log the wall-clock execution time of ``func`` at DEBUG level.

    The decorator is transparent: it preserves the wrapped function's signature,
    return value and metadata.
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        start = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            elapsed = time.perf_counter() - start
            logger.debug("{} executed in {:.3f}s", func.__qualname__, elapsed)

    return wrapper  # type: ignore[return-value]
