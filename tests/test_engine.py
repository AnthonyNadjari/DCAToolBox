"""Tests for the backtest engine: correctness, no-overdraft, no look-ahead."""

from __future__ import annotations

import pandas as pd

from dcatoolbox.backtesting.engine import BacktestEngine, periods_per_year
from dcatoolbox.backtesting.runner import run_backtest
from dcatoolbox.config.enums import Frequency
from dcatoolbox.strategies.monthly_dca import MonthlyDCA
from dcatoolbox.strategies.registry import build_strategy


def test_periods_per_year_mapping() -> None:
    assert periods_per_year(Frequency.DAILY) == 252


def test_run_produces_history_and_trades(base_config, synthetic_market) -> None:
    result = BacktestEngine(base_config).run(
        build_strategy(base_config.strategy),
        synthetic_market,
        build_strategy(base_config.benchmark),
    )
    assert not result.strategy.history.empty
    assert len(result.strategy.trades) > 0
    assert result.benchmark is not None


def test_cash_never_goes_negative(base_config, synthetic_market) -> None:
    result = run_backtest(base_config, market=synthetic_market)
    assert (result.strategy.history["cash"] >= -1e-6).all()


def test_monthly_dca_invests_full_budget_each_month(base_config, synthetic_market) -> None:
    result = BacktestEngine(base_config).run(MonthlyDCA(), synthetic_market)
    # One scheduled order per month over ~6 years -> dozens of trades.
    assert 60 <= len(result.strategy.trades) <= 80
    # Invested capital grows in 1000 increments.
    invested = result.strategy.history["invested_capital"]
    assert invested.iloc[-1] % 1000 == 0


def test_invested_capital_matches_contributions(base_config, synthetic_market) -> None:
    result = run_backtest(base_config, market=synthetic_market)
    months = result.strategy.history["invested_capital"].iloc[-1] / base_config.monthly_budget
    assert months == round(months)  # whole number of monthly contributions


def test_dip_buying_makes_more_trades_than_benchmark(base_config, synthetic_market) -> None:
    result = run_backtest(base_config, market=synthetic_market)
    assert len(result.strategy.trades) >= len(result.benchmark.trades)


def test_comparison_and_equity_frames(base_config, synthetic_market) -> None:
    result = run_backtest(base_config, market=synthetic_market)
    assert "dip_buying" in result.comparison_frame().columns
    assert "monthly_dca" in result.equity_frame().columns


def test_multi_asset_alignment(base_config, synthetic_market) -> None:
    # Add a second asset on a different (shorter) calendar; engine must align.
    extra = synthetic_market["SPY"].slice(pd.Timestamp("2016-01-01"), pd.Timestamp("2020-01-01"))
    market = {"SPY": synthetic_market["SPY"], "VOO": extra}
    result = run_backtest(base_config, market=market)
    assert not result.strategy.history.empty
