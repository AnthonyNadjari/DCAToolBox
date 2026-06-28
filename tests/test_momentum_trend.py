"""Tests for the trend-filter and momentum strategy families."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from dcatoolbox.backtesting.context import MarketContext
from dcatoolbox.portfolio.portfolio import Portfolio
from dcatoolbox.strategies.momentum import (
    AbsoluteMomentumStrategy,
    MomentumRotationStrategy,
)
from dcatoolbox.strategies.trend_filter import TrendFilterStrategy


def _frame(prices: list[float]) -> pd.DataFrame:
    idx = pd.bdate_range("2020-01-01", periods=len(prices), name="date")
    p = np.array(prices, dtype=float)
    return pd.DataFrame({"open": p, "high": p, "low": p, "close": p, "volume": 1.0}, index=idx)


def _ctx(
    histories: dict[str, pd.DataFrame], *, scheduled: bool = True, cash: float = 1000.0
) -> MarketContext:
    primary = next(iter(histories))
    return MarketContext(
        timestamp=histories[primary].index[-1],
        histories=histories,
        portfolio=Portfolio(initial_cash=cash),
        calendar=histories[primary].index,
        monthly_budget=1000.0,
        day_of_month=26,
        is_scheduled_day=scheduled,
        primary_ticker=primary,
    )


def test_trend_filter_skips_below_ma() -> None:
    falling = _frame(list(np.linspace(200, 100, 60)))
    assert TrendFilterStrategy(ma_window=20).on_bar(_ctx({"SPY": falling})) == []


def test_trend_filter_invests_above_ma() -> None:
    rising = _frame(list(np.linspace(100, 200, 60)))
    orders = TrendFilterStrategy(ma_window=20).on_bar(_ctx({"SPY": rising}))
    assert len(orders) == 1 and orders[0].notional == pytest.approx(1000.0)


def test_absolute_momentum_holds_on_negative() -> None:
    falling = _frame(list(np.linspace(200, 100, 60)))
    assert AbsoluteMomentumStrategy(lookback=20).on_bar(_ctx({"SPY": falling})) == []


def test_absolute_momentum_invests_on_positive() -> None:
    rising = _frame(list(np.linspace(100, 200, 60)))
    assert len(AbsoluteMomentumStrategy(lookback=20).on_bar(_ctx({"SPY": rising}))) == 1


def test_momentum_rotation_picks_strongest() -> None:
    weak = _frame([100] * 40 + list(np.linspace(100, 105, 20)))
    strong = _frame([100] * 40 + list(np.linspace(100, 160, 20)))
    orders = MomentumRotationStrategy(lookback=20).on_bar(_ctx({"SPY": weak, "QQQ": strong}))
    assert len(orders) == 1 and orders[0].ticker == "QQQ"


def test_momentum_rotation_dual_holds_when_all_negative() -> None:
    a = _frame(list(np.linspace(200, 100, 60)))
    b = _frame(list(np.linspace(180, 120, 60)))
    assert (
        MomentumRotationStrategy(lookback=20, absolute=True).on_bar(_ctx({"SPY": a, "QQQ": b}))
        == []
    )


def test_momentum_rotation_excludes_insufficient_history() -> None:
    # QQQ joins late (NaN before its first bar); it must be excluded, not ranked
    # on a NaN -- matching the in-browser JS engine.
    spy = _frame(list(np.linspace(100, 130, 60)))
    qqq = _frame([float("nan")] * 55 + [100.0, 101.0, 102.0, 103.0, 104.0])
    orders = MomentumRotationStrategy(lookback=20).on_bar(_ctx({"SPY": spy, "QQQ": qqq}))
    assert orders and orders[0].ticker == "SPY"


def test_validation_rejects_bad_params() -> None:
    with pytest.raises(ValueError):
        TrendFilterStrategy(ma_window=1)
    with pytest.raises(ValueError):
        AbsoluteMomentumStrategy(lookback=1)
