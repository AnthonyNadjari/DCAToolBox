"""Tests for the portfolio and position bookkeeping."""

from __future__ import annotations

import pandas as pd
import pytest

from dcatoolbox.broker.orders import Trade
from dcatoolbox.config.enums import OrderSide
from dcatoolbox.portfolio.portfolio import Portfolio
from dcatoolbox.portfolio.position import Position

TS = pd.Timestamp("2020-01-02")


def _buy(qty: float, price: float, fee: float = 0.0) -> Trade:
    return Trade(TS, "SPY", OrderSide.BUY, qty, price, fee, -(qty * price + fee), "test")


def test_position_average_price() -> None:
    pos = Position("SPY")
    pos.apply(_buy(10, 100))
    pos.apply(_buy(10, 120))
    assert pos.quantity == 20
    assert pos.average_price == pytest.approx(110.0)


def test_position_reduce_keeps_average() -> None:
    pos = Position("SPY")
    pos.apply(_buy(10, 100))
    pos.apply(Trade(TS, "SPY", OrderSide.SELL, 4, 150, 0.0, 600.0, ""))
    assert pos.quantity == pytest.approx(6.0)
    assert pos.average_price == pytest.approx(100.0)


def test_deposit_tracks_invested_capital() -> None:
    pf = Portfolio()
    pf.deposit(1000.0, TS)
    pf.deposit(500.0, TS)
    assert pf.cash == pytest.approx(1500.0)
    assert pf.invested_capital == pytest.approx(1500.0)


def test_apply_trade_updates_cash_and_fees() -> None:
    pf = Portfolio(initial_cash=1000.0)
    pf.apply_trade(_buy(5, 100, fee=2.5))
    assert pf.cash == pytest.approx(1000.0 - 502.5)
    assert pf.total_fees == pytest.approx(2.5)
    assert pf.total_quantity == pytest.approx(5.0)


def test_total_value_marks_to_market() -> None:
    pf = Portfolio(initial_cash=1000.0)
    pf.apply_trade(_buy(5, 100))
    assert pf.total_value({"SPY": 120.0}) == pytest.approx(500.0 + 5 * 120.0)


def test_history_records_snapshots() -> None:
    pf = Portfolio(initial_cash=1000.0)
    pf.apply_trade(_buy(5, 100))
    pf.record(TS, {"SPY": 110.0})
    hist = pf.history()
    assert list(hist.index) == [TS]
    assert hist.loc[TS, "total_value"] == pytest.approx(500.0 + 5 * 110.0)


def test_empty_history_has_expected_columns() -> None:
    hist = Portfolio().history()
    assert hist.empty
    assert "total_value" in hist.columns
