"""The single, dedicated class that groups every performance metric."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from dcatoolbox.broker.orders import Trade
from dcatoolbox.config.enums import OrderSide
from dcatoolbox.metrics.returns import (
    drawdown_series,
    external_flows,
    time_weighted_returns,
    wealth_index,
    xirr,
)

__all__ = ["PerformanceMetrics"]

_EPS = 1e-12


@dataclass
class _Scalars:
    """Container for all scalar metrics (kept separate for clean serialisation)."""

    total_return: float = 0.0
    twr_total_return: float = 0.0
    cagr: float = 0.0
    annual_return: float = 0.0
    annual_volatility: float = 0.0
    sharpe: float = 0.0
    sortino: float = 0.0
    calmar: float = 0.0
    max_drawdown: float = 0.0
    time_under_water: float = 0.0
    max_time_under_water_days: int = 0
    irr: float = 0.0
    xirr: float = 0.0
    tracking_error: float = 0.0
    information_ratio: float = 0.0
    n_orders: int = 0
    avg_order_amount: float = 0.0
    avg_buy_price: float = 0.0
    avg_cash: float = 0.0
    cumulative_fees: float = 0.0
    invested_capital: float = 0.0
    final_value: float = 0.0
    excess_total_return: float = 0.0
    excess_cagr: float = 0.0


class PerformanceMetrics:
    """Compute and hold the full performance / risk metric set for one backtest.

    All metrics are computed eagerly at construction. The class also retains the
    intermediate time series (returns, wealth index, drawdown) that the
    visualisation layer consumes.
    """

    def __init__(
        self,
        history: pd.DataFrame,
        trades: list[Trade],
        *,
        risk_free_rate: float = 0.02,
        periods_per_year: int = 252,
        benchmark_history: pd.DataFrame | None = None,
    ) -> None:
        """Compute every metric from a portfolio history and its trades."""
        self.history = history
        self.trades = trades
        self.risk_free_rate = risk_free_rate
        self.periods_per_year = periods_per_year
        self.returns = time_weighted_returns(history)
        self.wealth_index = wealth_index(history)
        self.drawdown = drawdown_series(self.wealth_index)
        self._scalars = _Scalars()
        if not history.empty:
            self._compute(benchmark_history)

    # ----- public API --------------------------------------------------------
    def as_dict(self) -> dict[str, float]:
        """Return all scalar metrics as a flat dictionary."""
        return asdict(self._scalars)

    def __getattr__(self, item: str) -> float:
        """Expose scalar metrics as attributes (e.g. ``metrics.sharpe``)."""
        scalars = self.__dict__.get("_scalars")
        if scalars is not None and hasattr(scalars, item):
            return getattr(scalars, item)
        raise AttributeError(item)

    def rolling_return(self, window: int = 252) -> pd.Series:
        """Rolling annualised return over ``window`` bars (TWR-based)."""
        return (1.0 + self.returns).rolling(window).apply(np.prod, raw=True) - 1.0

    def rolling_drawdown(self, window: int = 252) -> pd.Series:
        """Rolling maximum drawdown over a trailing ``window``."""
        return self.drawdown.rolling(window, min_periods=1).min()

    # ----- computation pipeline ---------------------------------------------
    def _compute(self, benchmark_history: pd.DataFrame | None) -> None:
        self._compute_return_metrics()
        self._compute_risk_metrics()
        self._compute_cashflow_metrics()
        self._compute_trade_metrics()
        if benchmark_history is not None and not benchmark_history.empty:
            self._compute_relative_metrics(benchmark_history)

    def _years(self) -> float:
        span = (self.history.index[-1] - self.history.index[0]).days
        return max(span / 365.25, _EPS)

    def _compute_return_metrics(self) -> None:
        s = self._scalars
        s.invested_capital = float(self.history["invested_capital"].iloc[-1])
        s.final_value = float(self.history["total_value"].iloc[-1])
        s.total_return = s.final_value / s.invested_capital - 1.0 if s.invested_capital else 0.0
        s.twr_total_return = (
            float(self.wealth_index.iloc[-1] - 1.0) if len(self.wealth_index) else 0.0
        )
        s.cagr = (
            float(self.wealth_index.iloc[-1] ** (1.0 / self._years()) - 1.0)
            if len(self.wealth_index)
            else 0.0
        )
        s.annual_return = float(self.returns.mean() * self.periods_per_year)

    def _compute_risk_metrics(self) -> None:
        s = self._scalars
        ppy = self.periods_per_year
        s.annual_volatility = (
            float(self.returns.std(ddof=1) * np.sqrt(ppy)) if len(self.returns) > 1 else 0.0
        )
        excess = s.annual_return - self.risk_free_rate
        s.sharpe = excess / s.annual_volatility if s.annual_volatility > _EPS else 0.0
        downside = self.returns[self.returns < 0]
        dd_vol = float(downside.std(ddof=1) * np.sqrt(ppy)) if len(downside) > 1 else 0.0
        s.sortino = excess / dd_vol if dd_vol > _EPS else 0.0
        s.max_drawdown = float(self.drawdown.min()) if len(self.drawdown) else 0.0
        s.calmar = s.cagr / abs(s.max_drawdown) if abs(s.max_drawdown) > _EPS else 0.0
        underwater = self.drawdown < -_EPS
        s.time_under_water = float(underwater.mean()) if len(underwater) else 0.0
        s.max_time_under_water_days = _longest_run(underwater)

    def _compute_cashflow_metrics(self) -> None:
        s = self._scalars
        flows = external_flows(self.history)
        dates = list(self.history.index)
        amounts = [-float(f) for f in flows]
        amounts.append(s.final_value)
        dates.append(self.history.index[-1])
        s.xirr = float(xirr(amounts, dates))
        s.irr = float((1.0 + s.xirr) ** (1.0 / 12.0) - 1.0) if np.isfinite(s.xirr) else float("nan")
        s.avg_cash = float(self.history["cash"].mean())
        s.cumulative_fees = float(self.history["cumulative_fees"].iloc[-1])

    def _compute_trade_metrics(self) -> None:
        s = self._scalars
        buys = [t for t in self.trades if t.side is OrderSide.BUY]
        s.n_orders = len(self.trades)
        if buys:
            s.avg_order_amount = float(np.mean([t.gross_value for t in buys]))
            total_qty = sum(t.quantity for t in buys)
            s.avg_buy_price = sum(t.gross_value for t in buys) / total_qty if total_qty else 0.0

    def _compute_relative_metrics(self, benchmark_history: pd.DataFrame) -> None:
        s = self._scalars
        bench_returns = time_weighted_returns(benchmark_history)
        active = (self.returns - bench_returns).dropna()
        ppy = self.periods_per_year
        s.tracking_error = float(active.std(ddof=1) * np.sqrt(ppy)) if len(active) > 1 else 0.0
        s.information_ratio = (
            float(active.mean() * ppy) / s.tracking_error if s.tracking_error > _EPS else 0.0
        )
        bench_invested = float(benchmark_history["invested_capital"].iloc[-1])
        bench_final = float(benchmark_history["total_value"].iloc[-1])
        bench_total = bench_final / bench_invested - 1.0 if bench_invested else 0.0
        bench_wi = wealth_index(benchmark_history)
        bench_years = max(
            (benchmark_history.index[-1] - benchmark_history.index[0]).days / 365.25, _EPS
        )
        bench_cagr = float(bench_wi.iloc[-1] ** (1.0 / bench_years) - 1.0) if len(bench_wi) else 0.0
        s.excess_total_return = s.total_return - bench_total
        s.excess_cagr = s.cagr - bench_cagr


def _longest_run(mask: pd.Series) -> int:
    """Length of the longest consecutive ``True`` run in a boolean series."""
    longest = current = 0
    for flag in mask:
        current = current + 1 if flag else 0
        longest = max(longest, current)
    return longest
