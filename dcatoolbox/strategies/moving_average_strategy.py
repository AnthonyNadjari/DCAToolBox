"""MovingAverageStrategy: a bonus strategy demonstrating extensibility.

Deploys budget when price trades a configurable margin below its moving average
(a mean-reversion style dip). Like every strategy, it is a single self-contained,
self-registering module.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

from dcatoolbox.strategies.budget_deployment import BudgetDeploymentStrategy, Signal
from dcatoolbox.strategies.indicators import sma
from dcatoolbox.strategies.registry import register_strategy

if TYPE_CHECKING:
    from dcatoolbox.backtesting.context import MarketContext

__all__ = ["MovingAverageStrategy"]


@register_strategy
class MovingAverageStrategy(BudgetDeploymentStrategy):
    """Buy when the close is ``margin`` below its ``window``-day moving average.

    Parameters (via ``params``):
        window: Moving-average look-back. Default ``50``.
        margin: Fractional distance below the average that triggers a buy
            (e.g. ``0.02`` = 2% below). Default ``0.0``.
        allocation: Fraction of remaining budget per signal. Default ``0.25``.
    """

    name = "moving_average"

    def _configure(self) -> None:
        self.window = int(self.params.get("window", 50))
        self.margin = float(self.params.get("margin", 0.0))

    def _signal(self, context: MarketContext) -> Signal:
        close = context.history["close"]
        if len(close) < self.window:
            return (False, "close")
        average = sma(close, self.window).iloc[-1]
        if pd.isna(average):
            return (False, "close")
        fired = bool(close.iloc[-1] < average * (1.0 - self.margin))
        return (fired, "close")
