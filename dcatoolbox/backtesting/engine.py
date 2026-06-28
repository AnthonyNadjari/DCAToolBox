"""The generic, strategy-agnostic backtest engine.

The engine knows nothing about any specific strategy: it only walks the calendar
chronologically, hands each strategy a look-ahead-free :class:`MarketContext`,
routes the returned orders through the broker and books them in the portfolio.
Adding a strategy never requires touching this file.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

from dcatoolbox.backtesting.context import MarketContext
from dcatoolbox.backtesting.result import BacktestResult, StrategyRun
from dcatoolbox.broker.broker import SimulatedBroker
from dcatoolbox.broker.orders import Order
from dcatoolbox.config.enums import Frequency, OrderSide
from dcatoolbox.config.settings import BacktestConfig
from dcatoolbox.data.models import MarketData
from dcatoolbox.metrics.performance import PerformanceMetrics
from dcatoolbox.portfolio.portfolio import Portfolio
from dcatoolbox.utils.calendar import month_start_days, scheduled_days
from dcatoolbox.utils.decorators import timed

if TYPE_CHECKING:
    from dcatoolbox.strategies.base import Strategy

__all__ = ["BacktestEngine", "periods_per_year"]

_PERIODS_PER_YEAR: dict[Frequency, int] = {
    Frequency.DAILY: 252,
    Frequency.HOURLY: 252 * 7,
    Frequency.INTRADAY: 252 * 26,
}


def periods_per_year(frequency: Frequency) -> int:
    """Number of bars per year for annualising metrics at a given frequency."""
    return _PERIODS_PER_YEAR[frequency]


class BacktestEngine:
    """Chronological, look-ahead-free simulation engine."""

    def __init__(self, config: BacktestConfig) -> None:
        """Create an engine bound to a configuration."""
        self.config = config

    @timed
    def run(
        self,
        strategy: Strategy,
        market: dict[str, MarketData],
        benchmark: Strategy | None = None,
    ) -> BacktestResult:
        """Run ``strategy`` (and optionally ``benchmark``) over ``market`` data."""
        aligned = self._align(market)
        strat_run = self._simulate(strategy, aligned)
        ppy = periods_per_year(self.config.data.frequency)
        bench_run = self._simulate(benchmark, aligned) if benchmark is not None else None
        bench_hist = bench_run.history if bench_run is not None else None
        strat_metrics = PerformanceMetrics(
            strat_run.history,
            strat_run.trades,
            risk_free_rate=self.config.risk_free_rate,
            periods_per_year=ppy,
            benchmark_history=bench_hist,
        )
        bench_metrics = (
            PerformanceMetrics(
                bench_run.history,
                bench_run.trades,
                risk_free_rate=self.config.risk_free_rate,
                periods_per_year=ppy,
            )
            if bench_run is not None
            else None
        )
        return BacktestResult(
            config=self.config,
            market=market,
            strategy=strat_run,
            strategy_metrics=strat_metrics,
            benchmark=bench_run,
            benchmark_metrics=bench_metrics,
        )

    def simulate(self, strategy: Strategy, market: dict[str, MarketData]) -> StrategyRun:
        """Simulate a single strategy and return its raw run (no metrics).

        Useful for the optimizer, which evaluates many strategies against one
        pre-computed benchmark and builds metrics itself.
        """
        return self._simulate(strategy, self._align(market))

    def _align(self, market: dict[str, MarketData]) -> dict[str, pd.DataFrame]:
        """Reindex every series onto the primary ticker's calendar (forward fill)."""
        primary = self.config.data.primary_ticker
        if primary not in market:
            raise KeyError(f"Primary ticker {primary} missing from market data")
        calendar = market[primary].frame.index
        aligned: dict[str, pd.DataFrame] = {}
        for ticker, data in market.items():
            frame = data.frame if ticker == primary else data.frame.reindex(calendar).ffill()
            aligned[ticker] = frame
        return aligned

    def _simulate(self, strategy: Strategy, aligned: dict[str, pd.DataFrame]) -> StrategyRun:
        """Core chronological loop for a single strategy."""
        primary = self.config.data.primary_ticker
        calendar = aligned[primary].index
        deposit_days = month_start_days(calendar)
        due_days = scheduled_days(calendar, self.config.day_of_month)
        portfolio = Portfolio(self.config.initial_cash)
        broker = SimulatedBroker(self.config.broker)
        strategy.reset()

        for i, timestamp in enumerate(calendar):
            if timestamp.normalize() in deposit_days:
                portfolio.deposit(self.config.monthly_budget, timestamp)
            context = MarketContext(
                timestamp=timestamp,
                histories={t: f.iloc[: i + 1] for t, f in aligned.items()},
                portfolio=portfolio,
                calendar=calendar,
                monthly_budget=self.config.monthly_budget,
                day_of_month=self.config.day_of_month,
                is_scheduled_day=timestamp.normalize() in due_days,
                primary_ticker=primary,
            )
            self._execute_orders(strategy.on_bar(context), aligned, i, timestamp, portfolio, broker)
            prices = {t: float(f["close"].iloc[i]) for t, f in aligned.items()}
            portfolio.record(timestamp, prices)

        return StrategyRun(
            name=strategy.name,
            params=dict(strategy.params),
            history=portfolio.history(),
            trades=broker.journal,
        )

    def _execute_orders(
        self,
        orders: list[Order],
        aligned: dict[str, pd.DataFrame],
        i: int,
        timestamp: pd.Timestamp,
        portfolio: Portfolio,
        broker: SimulatedBroker,
    ) -> None:
        """Execute every order for the current bar against current-bar prices."""
        for order in orders:
            reference = float(aligned[order.ticker][order.price_field].iloc[i])
            capped = self._cap_to_cash(order, portfolio.cash)
            if capped is None:
                continue
            trade = broker.execute(capped, reference, timestamp)
            portfolio.apply_trade(trade)

    @staticmethod
    def _cap_to_cash(order: Order, cash: float) -> Order | None:
        """Clip a notional buy to the available cash; never allow an overdraft."""
        if order.side is not OrderSide.BUY or order.notional is None:
            return order
        notional = min(order.notional, cash)
        if notional <= 0:
            return None
        if notional == order.notional:
            return order
        return Order(
            ticker=order.ticker,
            side=order.side,
            notional=notional,
            price_field=order.price_field,
            reason=order.reason,
        )
