"""RSIStrategy: a bonus strategy proving the framework's extensibility.

It deploys budget into oversold conditions (RSI below a threshold) and otherwise
behaves exactly like every other DCA strategy. It required *no* change to the
engine, the broker or the portfolio -- only this file.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

from dcatoolbox.strategies.budget_deployment import BudgetDeploymentStrategy, Signal
from dcatoolbox.strategies.indicators import rsi
from dcatoolbox.strategies.registry import register_strategy

if TYPE_CHECKING:
    from dcatoolbox.backtesting.context import MarketContext

__all__ = ["RSIStrategy"]


@register_strategy
class RSIStrategy(BudgetDeploymentStrategy):
    """Buy a fraction of remaining budget when RSI signals oversold.

    Parameters (via ``params``):
        period: RSI look-back period. Default ``14``.
        oversold: RSI level below which to buy. Default ``30``.
        allocation: Fraction of remaining budget per signal. Default ``0.25``.
    """

    name = "rsi"

    def _configure(self) -> None:
        self.period = int(self.params.get("period", 14))
        self.oversold = float(self.params.get("oversold", 30.0))

    def _signal(self, context: MarketContext) -> Signal:
        close = context.history["close"]
        if len(close) <= self.period:
            return (False, "close")
        latest = rsi(close, self.period).iloc[-1]
        fired = bool(pd.notna(latest) and latest < self.oversold)
        return (fired, "close")
