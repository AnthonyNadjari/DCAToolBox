"""Portfolio bookkeeping: cash, positions, contributions and daily history."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from dcatoolbox.broker.orders import Trade
from dcatoolbox.portfolio.position import Position

__all__ = ["Portfolio", "CashFlow"]


@dataclass(frozen=True)
class CashFlow:
    """An external contribution into (or withdrawal out of) the portfolio."""

    timestamp: pd.Timestamp
    amount: float  # positive = money paid in by the investor


class Portfolio:
    """Tracks cash, positions and a full daily history of the account.

    The portfolio is deliberately strategy-agnostic: it only knows how to take in
    contributions, apply executed trades and snapshot itself each day. All
    performance analytics are computed later by the metrics layer from the
    recorded history and cash flows.
    """

    def __init__(self, initial_cash: float = 0.0) -> None:
        """Create an empty portfolio seeded with ``initial_cash``."""
        self.cash: float = float(initial_cash)
        self.positions: dict[str, Position] = {}
        self.trades: list[Trade] = []
        self.cash_flows: list[CashFlow] = []
        self.total_fees: float = 0.0
        self._records: list[dict[str, float]] = []
        if initial_cash > 0:
            self.cash_flows.append(CashFlow(pd.Timestamp.min, float(initial_cash)))

    # ----- mutations ---------------------------------------------------------
    def deposit(self, amount: float, timestamp: pd.Timestamp) -> None:
        """Credit an external contribution and record it for IRR computations."""
        if amount <= 0:
            return
        self.cash += amount
        self.cash_flows.append(CashFlow(timestamp, float(amount)))

    def apply_trade(self, trade: Trade) -> None:
        """Apply an executed trade to cash and the relevant position."""
        position = self.positions.setdefault(trade.ticker, Position(trade.ticker))
        position.apply(trade)
        self.cash += trade.cash_flow
        self.total_fees += trade.fees
        self.trades.append(trade)

    def record(self, timestamp: pd.Timestamp, prices: dict[str, float]) -> None:
        """Append a daily snapshot of the account state."""
        positions_value = self.positions_value(prices)
        self._records.append(
            {
                "date": timestamp,
                "cash": self.cash,
                "positions_value": positions_value,
                "total_value": self.cash + positions_value,
                "invested_capital": self.invested_capital,
                "cumulative_fees": self.total_fees,
                "quantity": self.total_quantity,
                "n_trades": float(len(self.trades)),
            }
        )

    # ----- views -------------------------------------------------------------
    def positions_value(self, prices: dict[str, float]) -> float:
        """Mark-to-market value of all open positions."""
        return sum(
            pos.market_value(prices.get(ticker, 0.0)) for ticker, pos in self.positions.items()
        )

    def total_value(self, prices: dict[str, float]) -> float:
        """Cash plus the marked-to-market value of all positions."""
        return self.cash + self.positions_value(prices)

    @property
    def invested_capital(self) -> float:
        """Total external capital contributed so far."""
        return sum(cf.amount for cf in self.cash_flows)

    @property
    def total_quantity(self) -> float:
        """Aggregate share count across all positions."""
        return sum(pos.quantity for pos in self.positions.values())

    def history(self) -> pd.DataFrame:
        """Return the recorded daily history as a DataFrame indexed by date."""
        if not self._records:
            return pd.DataFrame(
                columns=[
                    "cash",
                    "positions_value",
                    "total_value",
                    "invested_capital",
                    "cumulative_fees",
                    "quantity",
                    "n_trades",
                ]
            )
        frame = pd.DataFrame(self._records).set_index("date")
        frame.index.name = "date"
        return frame
