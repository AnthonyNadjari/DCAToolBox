"""Tests for strategies, the registry and the shared deployment base."""

from __future__ import annotations

import pandas as pd
import pytest

from dcatoolbox.backtesting.context import MarketContext
from dcatoolbox.config.settings import StrategyConfig
from dcatoolbox.portfolio.portfolio import Portfolio
from dcatoolbox.strategies.dip_buying import DipBuyingStrategy
from dcatoolbox.strategies.monthly_dca import MonthlyDCA
from dcatoolbox.strategies.registry import (
    available_strategies,
    build_strategy,
    register_strategy,
)


def _context(history: pd.DataFrame, cash: float, *, scheduled: bool) -> MarketContext:
    pf = Portfolio(initial_cash=cash)
    return MarketContext(
        timestamp=history.index[-1],
        histories={"SPY": history},
        portfolio=pf,
        calendar=history.index,
        monthly_budget=1000.0,
        day_of_month=26,
        is_scheduled_day=scheduled,
        primary_ticker="SPY",
    )


def test_builtins_registered() -> None:
    for name in ("dip_buying", "monthly_dca", "rsi", "moving_average"):
        assert name in available_strategies()


def test_build_strategy_unknown_raises() -> None:
    with pytest.raises(KeyError):
        build_strategy(StrategyConfig(name="does_not_exist"))


def test_monthly_dca_invests_only_on_scheduled_day(small_frame) -> None:
    strat = MonthlyDCA()
    assert strat.on_bar(_context(small_frame, 1000.0, scheduled=False)) == []
    orders = strat.on_bar(_context(small_frame, 1000.0, scheduled=True))
    assert len(orders) == 1
    assert orders[0].notional == pytest.approx(1000.0)


def test_dip_buying_triggers_on_threshold_breach(small_frame) -> None:
    # Build a clear -5% open-over-open drop on the last bar.
    frame = small_frame.copy()
    frame.iloc[-2, frame.columns.get_loc("open")] = 100.0
    frame.iloc[-1, frame.columns.get_loc("open")] = 94.0
    strat = DipBuyingStrategy(threshold=0.02, allocation=0.25, signal_method="open_vs_open")
    orders = strat.on_bar(_context(frame, 1000.0, scheduled=False))
    assert len(orders) == 1
    assert orders[0].notional == pytest.approx(250.0)
    assert orders[0].reason == "dip"


def test_dip_buying_sweeps_remaining_on_scheduled_day(small_frame) -> None:
    strat = DipBuyingStrategy()
    orders = strat.on_bar(_context(small_frame, 750.0, scheduled=True))
    assert orders[0].notional == pytest.approx(750.0)
    assert orders[0].reason == "scheduled"


def test_dip_buying_no_order_without_signal(small_frame) -> None:
    frame = small_frame.copy()
    frame.iloc[-1, frame.columns.get_loc("open")] = frame["open"].iloc[-2] * 1.01  # up move
    strat = DipBuyingStrategy(threshold=0.02)
    assert strat.on_bar(_context(frame, 1000.0, scheduled=False)) == []


def test_dip_buying_validates_params() -> None:
    with pytest.raises(ValueError):
        DipBuyingStrategy(allocation=0.0)
    with pytest.raises(ValueError):
        DipBuyingStrategy(threshold=-0.01)


def test_no_orders_when_budget_exhausted(small_frame) -> None:
    assert MonthlyDCA().on_bar(_context(small_frame, 0.0, scheduled=True)) == []


def test_register_duplicate_name_raises() -> None:
    with pytest.raises(ValueError):

        @register_strategy
        class Dup(MonthlyDCA):
            name = "monthly_dca"


def test_describe_returns_params() -> None:
    desc = DipBuyingStrategy(threshold=0.03).describe()
    assert desc["name"] == "dip_buying"
    assert desc["params"]["threshold"] == 0.03
