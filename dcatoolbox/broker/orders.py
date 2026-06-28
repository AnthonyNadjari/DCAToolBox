"""Order and trade value objects exchanged between strategies and the broker."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from dcatoolbox.config.enums import OrderSide

__all__ = ["Order", "Trade"]


@dataclass(frozen=True)
class Order:
    """An instruction emitted by a strategy, to be executed by the broker.

    An order is specified either by ``notional`` (cash amount to commit, the
    natural unit for DCA) or by ``quantity`` (number of shares). Exactly one of
    the two must be provided.

    Attributes:
        ticker: Instrument to trade.
        side: Buy or sell.
        notional: Cash amount to commit (gross, fees included). Mutually
            exclusive with ``quantity``.
        quantity: Number of shares. Mutually exclusive with ``notional``.
        price_field: Bar field to execute against (``"open"`` or ``"close"``).
        reason: Free-form tag used for journaling/analytics (e.g. ``"dip"``).
    """

    ticker: str
    side: OrderSide = OrderSide.BUY
    notional: float | None = None
    quantity: float | None = None
    price_field: str = "open"
    reason: str = ""

    def __post_init__(self) -> None:
        if (self.notional is None) == (self.quantity is None):
            raise ValueError("Order requires exactly one of `notional` or `quantity`")
        if self.notional is not None and self.notional <= 0:
            raise ValueError("Order notional must be positive")
        if self.quantity is not None and self.quantity <= 0:
            raise ValueError("Order quantity must be positive")


@dataclass(frozen=True)
class Trade:
    """The realised outcome of executing an :class:`Order`.

    Attributes:
        timestamp: Execution timestamp.
        ticker: Instrument traded.
        side: Buy or sell.
        quantity: Shares actually transacted.
        price: Execution price *after* slippage.
        fees: Commission paid.
        cash_flow: Signed cash impact on the portfolio (negative for buys).
        reason: Propagated from the originating order.
    """

    timestamp: pd.Timestamp
    ticker: str
    side: OrderSide
    quantity: float
    price: float
    fees: float
    cash_flow: float
    reason: str = ""

    @property
    def gross_value(self) -> float:
        """Notional traded, excluding fees."""
        return self.quantity * self.price
