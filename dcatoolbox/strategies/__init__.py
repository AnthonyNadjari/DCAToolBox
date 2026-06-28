"""Strategy layer: base class, registry, signals and built-in strategies.

Importing this package eagerly loads the built-in strategies so they are present
in :data:`STRATEGY_REGISTRY` without any further action.
"""

from __future__ import annotations

# Eagerly register built-in strategies via import side effects.
from dcatoolbox.strategies import builtin  # noqa: E402,F401  (side-effect import)
from dcatoolbox.strategies.base import Strategy
from dcatoolbox.strategies.budget_deployment import BudgetDeploymentStrategy
from dcatoolbox.strategies.registry import (
    STRATEGY_REGISTRY,
    available_strategies,
    build_strategy,
    register_strategy,
)

__all__ = [
    "Strategy",
    "BudgetDeploymentStrategy",
    "STRATEGY_REGISTRY",
    "register_strategy",
    "build_strategy",
    "available_strategies",
]
