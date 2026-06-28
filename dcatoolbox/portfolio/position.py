"""Per-instrument position with running average cost."""

from __future__ import annotations

from dataclasses import dataclass

from dcatoolbox.broker.orders import Trade
from dcatoolbox.config.enums import OrderSide

__all__ = ["Position"]


@dataclass
class Position:
    """Holdings of a single instrument and its cost basis.

    Attributes:
        ticker: Instrument symbol.
        quantity: Number of shares currently held.
        cost_basis: Cumulative cash cost of the open shares, *excluding* fees
            (i.e. ``sum(qty_i * exec_price_i)``), used to derive the average buy
            price.
    """

    ticker: str
    quantity: float = 0.0
    cost_basis: float = 0.0

    @property
    def average_price(self) -> float:
        """Average purchase price of the open shares (0 when flat)."""
        return self.cost_basis / self.quantity if self.quantity > 0 else 0.0

    def apply(self, trade: Trade) -> None:
        """Update the position from an executed trade (average-cost method)."""
        if trade.side is OrderSide.BUY:
            self.quantity += trade.quantity
            self.cost_basis += trade.gross_value
        else:
            self._reduce(trade.quantity)

    def _reduce(self, quantity: float) -> None:
        """Reduce holdings by ``quantity`` keeping the average cost constant."""
        sold = min(quantity, self.quantity)
        if self.quantity > 0:
            self.cost_basis -= self.average_price * sold
        self.quantity -= sold

    def market_value(self, price: float) -> float:
        """Mark-to-market value of the position at ``price``."""
        return self.quantity * price
