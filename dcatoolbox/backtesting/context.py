"""The :class:`MarketContext` passed to a strategy on every bar.

The context is the *only* information a strategy receives. By construction it
exposes history strictly up to and including the current bar, which structurally
prevents look-ahead bias: a strategy simply cannot see the future.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from dcatoolbox.portfolio.portfolio import Portfolio

__all__ = ["MarketContext"]


@dataclass(frozen=True)
class MarketContext:
    """Immutable snapshot of everything a strategy may use to decide.

    Attributes:
        timestamp: The current bar's timestamp.
        histories: Per-ticker OHLCV frames truncated at ``timestamp`` (inclusive).
        portfolio: The live portfolio (read-only by convention).
        calendar: The full trading calendar of the backtest.
        monthly_budget: Cash contributed per month by the investment plan.
        day_of_month: Target day-of-month of the scheduled investment.
        is_scheduled_day: Whether ``timestamp`` is this month's scheduled day.
        primary_ticker: The default instrument to trade.
    """

    timestamp: pd.Timestamp
    histories: dict[str, pd.DataFrame]
    portfolio: Portfolio
    calendar: pd.DatetimeIndex
    monthly_budget: float
    day_of_month: int
    is_scheduled_day: bool
    primary_ticker: str

    @property
    def history(self) -> pd.DataFrame:
        """History of the primary ticker up to the current bar (inclusive)."""
        return self.histories[self.primary_ticker]

    @property
    def available_cash(self) -> float:
        """Uninvested cash, i.e. the budget still deployable this period."""
        return self.portfolio.cash

    def bar(self, ticker: str | None = None) -> pd.Series:
        """Return the latest (current) bar for ``ticker`` or the primary one."""
        return self.histories[ticker or self.primary_ticker].iloc[-1]

    def price(self, field: str = "close", ticker: str | None = None) -> float:
        """Return the current ``field`` price for ``ticker`` or the primary one."""
        return float(self.bar(ticker)[field])
