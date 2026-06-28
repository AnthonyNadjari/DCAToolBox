"""Abstract base class shared by every strategy.

A strategy is a pure decision function: given a :class:`MarketContext`, it returns
the list of orders to submit on that bar. It owns whatever internal state it
needs (and resets it via :meth:`reset`), but it never touches the broker,
portfolio internals or the engine loop. This is what lets the engine run *any*
strategy without modification.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from dcatoolbox.broker.orders import Order

if TYPE_CHECKING:
    from dcatoolbox.backtesting.context import MarketContext

__all__ = ["Strategy"]


class Strategy(ABC):
    """Base class for all investment strategies."""

    #: Unique registry name; concrete strategies must override this.
    name: str = "abstract"

    def __init__(self, **params: Any) -> None:
        """Store and validate strategy parameters."""
        self.params: dict[str, Any] = params
        self._validate()

    def _validate(self) -> None:
        """Validate ``self.params``; override to enforce strategy constraints."""

    def reset(self) -> None:
        """Reset any per-run internal state. Called once before each backtest."""

    @abstractmethod
    def on_bar(self, context: MarketContext) -> list[Order]:
        """Return the orders to submit for the current bar (possibly empty)."""
        raise NotImplementedError

    def describe(self) -> dict[str, Any]:
        """Return a serialisable description of the strategy and its parameters."""
        return {"name": self.name, "params": dict(self.params)}

    def __repr__(self) -> str:
        params = ", ".join(f"{k}={v!r}" for k, v in self.params.items())
        return f"{type(self).__name__}({params})"
