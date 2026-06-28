"""Simulated broker: order execution with fees, slippage and journaling."""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from dcatoolbox.broker.orders import Order, Trade
from dcatoolbox.config.enums import OrderSide
from dcatoolbox.config.settings import BrokerConfig
from dcatoolbox.utils.logging import logger

__all__ = ["Broker", "SimulatedBroker"]


class Broker(ABC):
    """Abstract execution venue."""

    @abstractmethod
    def execute(self, order: Order, reference_price: float, timestamp: pd.Timestamp) -> Trade:
        """Execute ``order`` against ``reference_price`` and return a :class:`Trade`."""
        raise NotImplementedError


class SimulatedBroker(Broker):
    """A deterministic broker applying proportional fees and slippage.

    Cost model for a *buy* of ``notional`` cash:

    * execution price ``p = ref * (1 + slippage)``
    * fee ``= max(notional * fee_rate, min_fee)``
    * shares bought ``= (notional - fee) / p``
    * cash out ``= notional`` (so the committed budget is never exceeded)

    Sells mirror the logic with slippage applied downwards.
    """

    def __init__(self, config: BrokerConfig | None = None) -> None:
        """Create the broker with the given cost assumptions."""
        self.config = config or BrokerConfig()
        self._journal: list[Trade] = []

    @property
    def journal(self) -> list[Trade]:
        """Chronological list of all executed trades."""
        return list(self._journal)

    def execute(self, order: Order, reference_price: float, timestamp: pd.Timestamp) -> Trade:
        """Execute ``order`` and record it in the journal."""
        if reference_price <= 0:
            raise ValueError("reference_price must be positive")
        trade = (
            self._execute_buy(order, reference_price, timestamp)
            if order.side is OrderSide.BUY
            else self._execute_sell(order, reference_price, timestamp)
        )
        self._journal.append(trade)
        logger.debug(
            "Executed {} {:.4f} {} @ {:.4f} (fees={:.2f}, reason={})",
            trade.side.value,
            trade.quantity,
            trade.ticker,
            trade.price,
            trade.fees,
            trade.reason,
        )
        return trade

    def _execute_buy(self, order: Order, ref: float, ts: pd.Timestamp) -> Trade:
        price = ref * (1.0 + self.config.slippage_rate)
        if order.notional is not None:
            fee = max(order.notional * self.config.fee_rate, self.config.min_fee)
            investable = max(order.notional - fee, 0.0)
            quantity = investable / price
            cash_flow = -order.notional
        else:
            quantity = order.quantity or 0.0
            gross = quantity * price
            fee = max(gross * self.config.fee_rate, self.config.min_fee)
            cash_flow = -(gross + fee)
        return Trade(ts, order.ticker, OrderSide.BUY, quantity, price, fee, cash_flow, order.reason)

    def _execute_sell(self, order: Order, ref: float, ts: pd.Timestamp) -> Trade:
        price = ref * (1.0 - self.config.slippage_rate)
        if order.quantity is None:
            raise ValueError("Sell orders must specify `quantity`")
        gross = order.quantity * price
        fee = max(gross * self.config.fee_rate, self.config.min_fee)
        cash_flow = gross - fee
        return Trade(
            ts, order.ticker, OrderSide.SELL, order.quantity, price, fee, cash_flow, order.reason
        )

    def reset(self) -> None:
        """Clear the trade journal (used between independent backtests)."""
        self._journal.clear()
