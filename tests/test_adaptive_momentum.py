"""Tests for the walk-forward adaptive momentum strategy."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from dcatoolbox.backtesting.context import MarketContext
from dcatoolbox.portfolio.portfolio import Portfolio
from dcatoolbox.strategies.adaptive_momentum import AdaptiveMomentumStrategy


def _frame(prices: list[float]) -> pd.DataFrame:
    idx = pd.bdate_range("2018-01-01", periods=len(prices), name="date")
    p = np.array(prices, dtype=float)
    return pd.DataFrame({"open": p, "high": p, "low": p, "close": p, "volume": 1.0}, index=idx)


def _ctx(
    histories: dict[str, pd.DataFrame], *, scheduled: bool = False, cash: float = 1000.0
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


def test_validation() -> None:
    with pytest.raises(ValueError):
        AdaptiveMomentumStrategy(check_every=0)
    with pytest.raises(ValueError):
        AdaptiveMomentumStrategy(horizons=[1])
    with pytest.raises(ValueError):
        AdaptiveMomentumStrategy(hi_threshold=0.0, lo_threshold=0.1)


def test_buys_leader_on_check_day() -> None:
    # 300 bars; bar index 299 is not a multiple of 5 -> pad to land on one.
    n = 301  # bar index 300 % 5 == 0
    weak = _frame(list(np.linspace(100, 110, n)))
    strong = _frame(list(np.linspace(100, 180, n)))
    strat = AdaptiveMomentumStrategy(check_every=5, horizons=[21, 63], dip_boost=0.0)
    orders = strat.on_bar(_ctx({"SPY": weak, "QQQ": strong}))
    assert len(orders) == 1 and orders[0].ticker == "QQQ"


def test_quiet_between_check_days() -> None:
    n = 302  # bar index 301 % 5 != 0
    strong = _frame(list(np.linspace(100, 180, n)))
    strat = AdaptiveMomentumStrategy(check_every=5, horizons=[21, 63])
    assert strat.on_bar(_ctx({"SPY": strong})) == []


def test_holds_cash_below_lo_threshold() -> None:
    n = 301
    falling = _frame(list(np.linspace(200, 100, n)))
    strat = AdaptiveMomentumStrategy(check_every=5, horizons=[21, 63], dip_boost=0.0)
    assert strat.on_bar(_ctx({"SPY": falling})) == []


def test_conviction_deploys_tranche_vs_all() -> None:
    n = 301
    # Slow riser: blended momentum small and positive -> one monthly tranche.
    slow = _frame(list(np.linspace(100, 104, n)))
    strat = AdaptiveMomentumStrategy(check_every=5, horizons=[21, 63], dip_boost=0.0)
    orders = strat.on_bar(_ctx({"SPY": slow}, cash=5000.0))
    assert len(orders) == 1 and orders[0].notional == pytest.approx(1000.0)
    # Fast riser (0.5%/bar compounding: 21-bar ~ +11%, 63-bar ~ +37%): blended
    # momentum clears hi_threshold -> the whole reserve deploys.
    fast = _frame(list(100 * 1.005 ** np.arange(n)))
    strat.reset()
    orders = strat.on_bar(_ctx({"SPY": fast}, cash=5000.0))
    assert len(orders) == 1 and orders[0].notional == pytest.approx(5000.0)


def test_weights_recalibrate_from_history() -> None:
    n = 900
    rng = np.random.default_rng(7)
    trend = np.cumprod(1 + 0.0004 + 0.01 * rng.standard_normal(n)) * 100
    strat = AdaptiveMomentumStrategy(check_every=5, horizons=[21, 63, 126])
    strat.on_bar(_ctx({"SPY": _frame(list(trend))}))
    assert strat._weights.shape == (3,)
    assert np.isclose(strat._weights.sum(), 1.0)
