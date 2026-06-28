"""High-level helpers tying data loading, strategy building and the engine.

These are the convenience entry points used by the CLI and the web UI; they keep
the wiring in one place so callers only deal with a :class:`BacktestConfig`.
"""

from __future__ import annotations

from dcatoolbox.backtesting.engine import BacktestEngine
from dcatoolbox.backtesting.result import BacktestResult
from dcatoolbox.config.settings import BacktestConfig
from dcatoolbox.data.factory import DataService
from dcatoolbox.data.models import MarketData
from dcatoolbox.strategies.registry import build_strategy

__all__ = ["load_market", "run_backtest"]


def load_market(config: BacktestConfig) -> dict[str, MarketData]:
    """Load all configured tickers via the data service."""
    return DataService(config.data).load_many()


def run_backtest(
    config: BacktestConfig,
    *,
    market: dict[str, MarketData] | None = None,
    with_benchmark: bool = True,
) -> BacktestResult:
    """Load data (unless provided), build strategies and run the engine.

    Args:
        config: Full backtest configuration.
        market: Optionally pre-loaded market data (avoids re-downloading).
        with_benchmark: Whether to also simulate the configured benchmark.

    Returns:
        A populated :class:`BacktestResult`.
    """
    market = market if market is not None else load_market(config)
    strategy = build_strategy(config.strategy)
    benchmark = build_strategy(config.benchmark) if with_benchmark else None
    return BacktestEngine(config).run(strategy, market, benchmark)
