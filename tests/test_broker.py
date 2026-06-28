"""Tests for the simulated broker and order/trade value objects."""

from __future__ import annotations

import pandas as pd
import pytest

from dcatoolbox.broker.broker import SimulatedBroker
from dcatoolbox.broker.orders import Order
from dcatoolbox.config.enums import OrderSide
from dcatoolbox.config.settings import BrokerConfig

TS = pd.Timestamp("2020-01-02")


def test_order_requires_exactly_one_of_notional_quantity() -> None:
    with pytest.raises(ValueError):
        Order("SPY", notional=100, quantity=1)
    with pytest.raises(ValueError):
        Order("SPY")


def test_notional_buy_never_exceeds_budget() -> None:
    broker = SimulatedBroker(BrokerConfig(fee_rate=0.005, slippage_rate=0.0005))
    trade = broker.execute(Order("SPY", notional=1000.0), reference_price=100.0, timestamp=TS)
    assert trade.cash_flow == pytest.approx(-1000.0)
    # shares * price + fee == notional committed
    assert trade.gross_value + trade.fees == pytest.approx(1000.0, rel=1e-9)


def test_slippage_raises_buy_price() -> None:
    broker = SimulatedBroker(BrokerConfig(fee_rate=0.0, slippage_rate=0.01))
    trade = broker.execute(Order("SPY", notional=100.0), reference_price=100.0, timestamp=TS)
    assert trade.price == pytest.approx(101.0)


def test_quantity_buy_cash_flow_includes_fees() -> None:
    broker = SimulatedBroker(BrokerConfig(fee_rate=0.01, slippage_rate=0.0))
    trade = broker.execute(Order("SPY", quantity=10.0), reference_price=50.0, timestamp=TS)
    assert trade.cash_flow == pytest.approx(-(500.0 + 5.0))


def test_sell_returns_cash_minus_fees() -> None:
    broker = SimulatedBroker(BrokerConfig(fee_rate=0.01, slippage_rate=0.0))
    trade = broker.execute(Order("SPY", side=OrderSide.SELL, quantity=10.0), 50.0, TS)
    assert trade.side is OrderSide.SELL
    assert trade.cash_flow == pytest.approx(500.0 - 5.0)


def test_sell_without_quantity_raises() -> None:
    broker = SimulatedBroker()
    with pytest.raises(ValueError):
        broker.execute(Order("SPY", side=OrderSide.SELL, notional=100.0), 50.0, TS)


def test_journal_records_and_resets() -> None:
    broker = SimulatedBroker()
    broker.execute(Order("SPY", notional=100.0), 100.0, TS)
    assert len(broker.journal) == 1
    broker.reset()
    assert broker.journal == []


def test_negative_reference_price_rejected() -> None:
    with pytest.raises(ValueError):
        SimulatedBroker().execute(Order("SPY", notional=100.0), -1.0, TS)


def test_min_fee_applied() -> None:
    broker = SimulatedBroker(BrokerConfig(fee_rate=0.0, slippage_rate=0.0, min_fee=2.0))
    trade = broker.execute(Order("SPY", notional=100.0), 100.0, TS)
    assert trade.fees == pytest.approx(2.0)
