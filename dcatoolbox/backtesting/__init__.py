"""Backtesting layer: context, generic engine, results and high-level runner."""

from __future__ import annotations

from dcatoolbox.backtesting.context import MarketContext
from dcatoolbox.backtesting.engine import BacktestEngine, periods_per_year
from dcatoolbox.backtesting.result import BacktestResult, StrategyRun
from dcatoolbox.backtesting.runner import load_market, run_backtest

__all__ = [
    "MarketContext",
    "BacktestResult",
    "StrategyRun",
    "BacktestEngine",
    "periods_per_year",
    "load_market",
    "run_backtest",
]
