"""Strategy registry and factory.

Strategies self-register via the :func:`register_strategy` decorator, so adding a
new strategy is purely additive: drop a new module, decorate the class, and it is
instantly available to the CLI, the optimizer and the web UI -- with **zero**
changes to the engine.
"""

from __future__ import annotations

from collections.abc import Callable

from dcatoolbox.config.settings import StrategyConfig
from dcatoolbox.strategies.base import Strategy

__all__ = ["register_strategy", "build_strategy", "available_strategies", "STRATEGY_REGISTRY"]

#: Maps a strategy name to its class.
STRATEGY_REGISTRY: dict[str, type[Strategy]] = {}


def register_strategy(cls: type[Strategy]) -> type[Strategy]:
    """Class decorator registering ``cls`` under its ``name`` attribute."""
    name = cls.name
    if name in {"", "abstract"}:
        raise ValueError(f"{cls.__name__} must define a unique `name`")
    if name in STRATEGY_REGISTRY and STRATEGY_REGISTRY[name] is not cls:
        raise ValueError(f"Strategy name '{name}' is already registered")
    STRATEGY_REGISTRY[name] = cls
    return cls


def build_strategy(config: StrategyConfig) -> Strategy:
    """Instantiate the strategy named in ``config`` with its parameters."""
    if config.name not in STRATEGY_REGISTRY:
        raise KeyError(f"Unknown strategy '{config.name}'. Available: {sorted(STRATEGY_REGISTRY)}")
    return STRATEGY_REGISTRY[config.name](**config.params)


def available_strategies() -> list[str]:
    """Return the sorted names of all registered strategies."""
    return sorted(STRATEGY_REGISTRY)


def _ensure_builtins_loaded(_loader: Callable[[], None] | None = None) -> None:
    """Import built-in strategy modules so they self-register (idempotent)."""
    from dcatoolbox.strategies import builtin  # noqa: F401  (import side effects)
