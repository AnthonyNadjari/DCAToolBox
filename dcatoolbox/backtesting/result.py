"""Result containers returned by the backtest engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from dcatoolbox.broker.orders import Trade
from dcatoolbox.config.settings import BacktestConfig
from dcatoolbox.data.models import MarketData
from dcatoolbox.metrics.performance import PerformanceMetrics

__all__ = ["StrategyRun", "BacktestResult"]


@dataclass
class StrategyRun:
    """Raw output of simulating a single strategy.

    Attributes:
        name: Strategy registry name.
        params: Strategy parameters used.
        history: Daily portfolio history (indexed by date).
        trades: Chronological list of executed trades.
    """

    name: str
    params: dict[str, Any]
    history: pd.DataFrame
    trades: list[Trade] = field(default_factory=list)


@dataclass
class BacktestResult:
    """A strategy run, its benchmark run and the computed metrics for both."""

    config: BacktestConfig
    market: dict[str, MarketData]
    strategy: StrategyRun
    strategy_metrics: PerformanceMetrics
    benchmark: StrategyRun | None = None
    benchmark_metrics: PerformanceMetrics | None = None

    @property
    def primary_ticker(self) -> str:
        """The instrument the backtest traded by default."""
        return self.config.data.primary_ticker

    def comparison_frame(self) -> pd.DataFrame:
        """Side-by-side table of strategy vs benchmark scalar metrics."""
        data: dict[str, dict[str, float]] = {self.strategy.name: self.strategy_metrics.as_dict()}
        if self.benchmark_metrics is not None and self.benchmark is not None:
            data[self.benchmark.name] = self.benchmark_metrics.as_dict()
        return pd.DataFrame(data)

    def equity_frame(self) -> pd.DataFrame:
        """Aligned total-value curves of the strategy and (if any) benchmark."""
        frame = pd.DataFrame({self.strategy.name: self.strategy.history["total_value"]})
        if self.benchmark is not None:
            frame[self.benchmark.name] = self.benchmark.history["total_value"]
        return frame
