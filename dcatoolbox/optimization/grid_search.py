"""Parallel grid-search optimizer with train/validation/test evaluation."""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Any

import pandas as pd
from joblib import Parallel, delayed

from dcatoolbox.backtesting.engine import BacktestEngine, periods_per_year
from dcatoolbox.backtesting.runner import run_backtest
from dcatoolbox.config.settings import BacktestConfig, OptimizationConfig, SplitConfig
from dcatoolbox.data.models import MarketData
from dcatoolbox.metrics.performance import PerformanceMetrics
from dcatoolbox.optimization.splitter import DataSplitter
from dcatoolbox.strategies.registry import build_strategy
from dcatoolbox.utils.logging import logger

__all__ = ["GridSearchOptimizer", "OptimizationResult", "SplitEvaluation"]


@dataclass
class OptimizationResult:
    """Ranked results of a grid search."""

    results: pd.DataFrame
    rank_metric: str
    maximize: bool
    param_names: list[str]

    @property
    def best_row(self) -> pd.Series:
        """The single best-scoring parameter combination."""
        return self.results.iloc[0]

    @property
    def best_params(self) -> dict[str, Any]:
        """Best parameters as a plain dict (ready for ``with_strategy_params``)."""
        return {name: self.best_row[name] for name in self.param_names}

    def leaderboard(self, top: int = 10) -> pd.DataFrame:
        """The top ``top`` combinations with their parameters and key metrics."""
        cols = self.param_names + [self.rank_metric, "cagr", "max_drawdown", "total_return"]
        present = [c for c in cols if c in self.results.columns]
        return self.results[present].head(top).reset_index(drop=True)


@dataclass
class SplitEvaluation:
    """Anti-overfitting view: best params evaluated per train/val/test window."""

    train_optimization: OptimizationResult
    best_params: dict[str, Any]
    per_window: pd.DataFrame


def _evaluate_combo(
    config: BacktestConfig,
    params: dict[str, Any],
    market: dict[str, MarketData],
    ppy: int,
    benchmark_history: pd.DataFrame,
) -> dict[str, Any]:
    """Run one parameter combination and return its params + scalar metrics.

    Defined at module level so it is picklable by :mod:`joblib`'s process pool.
    """
    variant = config.with_strategy_params(**params)
    strategy = build_strategy(variant.strategy)
    run = BacktestEngine(variant).simulate(strategy, market)
    metrics = PerformanceMetrics(
        run.history,
        run.trades,
        risk_free_rate=config.risk_free_rate,
        periods_per_year=ppy,
        benchmark_history=benchmark_history,
    )
    return {**params, **metrics.as_dict()}


class GridSearchOptimizer:
    """Exhaustive grid search over a strategy's parameter space."""

    def __init__(
        self, config: BacktestConfig, opt_config: OptimizationConfig | None = None
    ) -> None:
        """Bind the optimizer to a base config and an optimization spec."""
        self.config = config
        self.opt_config = opt_config or OptimizationConfig()

    def _combinations(self) -> list[dict[str, Any]]:
        """Cartesian product of every parameter value in the grid."""
        grid = self.opt_config.param_grid
        names = list(grid)
        return [
            dict(zip(names, values, strict=True)) for values in itertools.product(*grid.values())
        ]

    def run(self, market: dict[str, MarketData]) -> OptimizationResult:
        """Evaluate every combination and return a ranked result."""
        combos = self._combinations()
        ppy = periods_per_year(self.config.data.frequency)
        benchmark = build_strategy(self.config.benchmark)
        bench_history = BacktestEngine(self.config).simulate(benchmark, market).history
        logger.info(
            "Grid search over {} combinations ({} jobs)", len(combos), self.opt_config.n_jobs
        )
        rows = Parallel(n_jobs=self.opt_config.n_jobs)(
            delayed(_evaluate_combo)(self.config, c, market, ppy, bench_history) for c in combos
        )
        frame = pd.DataFrame(list(rows))
        frame = frame.sort_values(
            self.opt_config.rank_metric, ascending=not self.opt_config.maximize
        ).reset_index(drop=True)
        return OptimizationResult(
            results=frame,
            rank_metric=self.opt_config.rank_metric,
            maximize=self.opt_config.maximize,
            param_names=list(self.opt_config.param_grid),
        )

    def evaluate_splits(self, market: dict[str, MarketData], split: SplitConfig) -> SplitEvaluation:
        """Fit on train, then report the best params on each split separately."""
        windows = DataSplitter(split).split_market(market)
        train_result = self.run(windows["train"])
        best = train_result.best_params
        rows = []
        for name, window_market in windows.items():
            variant = self.config.with_strategy_params(**best)
            result = run_backtest(variant, market=window_market)
            rows.append({"window": name, **result.strategy_metrics.as_dict()})
        per_window = pd.DataFrame(rows).set_index("window")
        return SplitEvaluation(train_result, best, per_window)
