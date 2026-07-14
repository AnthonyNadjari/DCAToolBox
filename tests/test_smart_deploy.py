"""Tests for the smart-deployment (target weights + pacing) strategy."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from dcatoolbox.backtesting.context import MarketContext
from dcatoolbox.portfolio.portfolio import Portfolio
from dcatoolbox.portfolio.position import Position
from dcatoolbox.strategies.smart_deploy import SmartDeployStrategy


def _frame(prices: list[float]) -> pd.DataFrame:
    idx = pd.bdate_range("2018-01-01", periods=len(prices), name="date")
    p = np.array(prices, dtype=float)
    return pd.DataFrame({"open": p, "high": p, "low": p, "close": p, "volume": 1.0}, index=idx)


def _ctx(histories, *, cash=1000.0, scheduled=False) -> MarketContext:
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


def _rising(n: int, rate: float = 1.003) -> pd.DataFrame:
    return _frame(list(100 * rate ** np.arange(n)))


def test_validation() -> None:
    with pytest.raises(ValueError):
        SmartDeployStrategy(scheme="nope")
    with pytest.raises(ValueError):
        SmartDeployStrategy(deploy_rate=0.0)


def test_guard_holds_cash_when_all_falling() -> None:
    falling = _frame(list(np.linspace(200, 100, 300)))
    strat = SmartDeployStrategy(scheme="softmax", horizons=[21, 63])
    assert strat.on_bar(_ctx({"A": falling, "B": falling})) == []


def test_winner_buys_leader_with_all_cash() -> None:
    weak = _rising(300, 1.0005)
    strong = _rising(300, 1.004)
    strat = SmartDeployStrategy(scheme="winner", horizons=[21, 63], deploy_rate=1.0)
    orders = strat.on_bar(_ctx({"A": weak, "B": strong}, cash=2000.0))
    assert len(orders) == 1 and orders[0].ticker == "B"
    assert orders[0].notional == pytest.approx(2000.0)


def test_deploy_rate_paces_the_cash() -> None:
    strong = _rising(300, 1.004)
    strat = SmartDeployStrategy(scheme="winner", horizons=[21, 63], deploy_rate=0.2)
    orders = strat.on_bar(_ctx({"A": strong}, cash=1000.0))
    assert len(orders) == 1 and orders[0].notional == pytest.approx(200.0)


def test_softmax_buys_most_underweight() -> None:
    a = _rising(300, 1.002)
    b = _rising(300, 1.0021)  # nearly identical momentum -> weights ~50/50
    ctx = _ctx({"A": a, "B": b}, cash=1000.0)
    # Already loaded with A: the flow must go to B (most underweight).
    ctx.portfolio.positions["A"] = Position("A", quantity=50.0, cost_basis=5000.0)
    strat = SmartDeployStrategy(scheme="softmax", softmax_k=5, horizons=[21, 63])
    orders = strat.on_bar(ctx)
    assert len(orders) == 1 and orders[0].ticker == "B"


def test_dip_accelerator_boosts_investable() -> None:
    n = 300
    prices = list(100 * 1.003 ** np.arange(n - 5))
    prices += [prices[-1] * 0.93] * 5  # 7% below the 20-day high, trend intact
    dipped = _frame(prices)
    base = SmartDeployStrategy(scheme="winner", horizons=[63], deploy_rate=0.1)
    boosted = SmartDeployStrategy(
        scheme="winner", horizons=[63], deploy_rate=0.1, dip_accel=3.0, dip_threshold=0.05
    )
    plain = base.on_bar(_ctx({"A": dipped}, cash=1000.0))
    accel = boosted.on_bar(_ctx({"A": dipped}, cash=1000.0))
    assert plain[0].notional == pytest.approx(100.0)
    assert accel[0].notional == pytest.approx(300.0)


def test_vol_target_caps_equity_share() -> None:
    rng = np.random.default_rng(3)
    wild = _frame(list(100 * np.cumprod(1 + 0.002 + 0.03 * rng.standard_normal(300))))
    strat = SmartDeployStrategy(scheme="winner", horizons=[63], vol_target=0.10)
    ctx = _ctx({"A": wild}, cash=10_000.0)
    orders = strat.on_bar(ctx)
    # Realised vol of this series is far above 10%: only a fraction may deploy.
    assert not orders or orders[0].notional < 10_000.0


def test_fixed_weights_buy_most_underweight() -> None:
    a = _rising(300, 1.002)
    b = _rising(300, 1.002)
    ctx = _ctx({"A": a, "B": b}, cash=1000.0)
    ctx.portfolio.positions["A"] = Position("A", quantity=100.0, cost_basis=10_000.0)
    strat = SmartDeployStrategy(
        scheme="fixed", guard=False, weights={"A": 0.7, "B": 0.3}, horizons=[21, 63]
    )
    orders = strat.on_bar(ctx)
    # A is overweight vs its 70% target -> the flow must go to B.
    assert len(orders) == 1 and orders[0].ticker == "B"
