"""Minimal end-to-end example: run a backtest and print the comparison table.

Run with::

    python examples/quickstart.py

It uses the deterministic synthetic data provider so it works fully offline.
"""

from __future__ import annotations

from datetime import date

from dcatoolbox.backtesting import run_backtest
from dcatoolbox.config.enums import ProviderType
from dcatoolbox.config.settings import BacktestConfig, DataConfig, StrategyConfig


def main() -> None:
    """Build a config, run a backtest and print metrics."""
    config = BacktestConfig(
        data=DataConfig(
            provider=ProviderType.SYNTHETIC,
            tickers=["SPY"],
            start=date(2010, 1, 1),
            end=date(2024, 1, 1),
        ),
        strategy=StrategyConfig(
            name="dip_buying",
            params={"threshold": 0.02, "allocation": 0.25, "signal_method": "open_vs_open"},
        ),
        benchmark=StrategyConfig(name="monthly_dca"),
        monthly_budget=1000.0,
        day_of_month=26,
    )
    result = run_backtest(config)
    print(result.comparison_frame().round(4).to_string())


if __name__ == "__main__":
    main()
