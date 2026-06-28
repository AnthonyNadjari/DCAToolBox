"""Tests for technical indicators and the bonus strategies."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from dcatoolbox.backtesting.context import MarketContext
from dcatoolbox.portfolio.portfolio import Portfolio
from dcatoolbox.strategies.indicators import rsi, sma
from dcatoolbox.strategies.moving_average_strategy import MovingAverageStrategy
from dcatoolbox.strategies.rsi_strategy import RSIStrategy


def _context(history: pd.DataFrame, cash: float = 1000.0) -> MarketContext:
    return MarketContext(
        timestamp=history.index[-1],
        histories={"SPY": history},
        portfolio=Portfolio(initial_cash=cash),
        calendar=history.index,
        monthly_budget=1000.0,
        day_of_month=26,
        is_scheduled_day=False,
        primary_ticker="SPY",
    )


def test_sma_matches_manual() -> None:
    series = pd.Series([1.0, 2.0, 3.0, 4.0])
    assert sma(series, 2).iloc[-1] == pytest.approx(3.5)


def test_rsi_bounds_and_extremes() -> None:
    rising = pd.Series(np.arange(1, 50, dtype=float))
    value = rsi(rising, 14).iloc[-1]
    assert 0.0 <= value <= 100.0
    assert value > 90.0  # uninterrupted gains -> very high RSI


def test_rsi_strategy_triggers_when_oversold() -> None:
    falling = np.linspace(200, 100, 40)
    frame = pd.DataFrame(
        {"open": falling, "high": falling, "low": falling, "close": falling, "volume": 1.0},
        index=pd.bdate_range("2020-01-01", periods=40, name="date"),
    )
    strat = RSIStrategy(oversold=40, period=14, allocation=0.5)
    fired, field = strat._signal(_context(frame))
    assert fired is True
    assert field == "close"


def test_rsi_strategy_insufficient_history() -> None:
    frame = pd.DataFrame(
        {"open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0], "volume": [1.0]},
        index=pd.bdate_range("2020-01-01", periods=1, name="date"),
    )
    assert RSIStrategy()._signal(_context(frame))[0] is False


def test_moving_average_strategy_triggers_below_average() -> None:
    prices = [100.0] * 49 + [80.0]
    frame = pd.DataFrame(
        {"open": prices, "high": prices, "low": prices, "close": prices, "volume": 1.0},
        index=pd.bdate_range("2020-01-01", periods=50, name="date"),
    )
    strat = MovingAverageStrategy(window=50, margin=0.05)
    fired, _ = strat._signal(_context(frame))
    assert fired is True


def test_moving_average_insufficient_history() -> None:
    prices = [100.0] * 10
    frame = pd.DataFrame(
        {"open": prices, "high": prices, "low": prices, "close": prices, "volume": 1.0},
        index=pd.bdate_range("2020-01-01", periods=10, name="date"),
    )
    assert MovingAverageStrategy(window=50)._signal(_context(frame))[0] is False
