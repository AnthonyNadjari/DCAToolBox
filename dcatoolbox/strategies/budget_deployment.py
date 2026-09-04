"""Reusable base for budget-deploying, signal-triggered DCA strategies.

Many strategies share the exact same skeleton: each month deploy a fraction of
the remaining budget whenever some condition fires, and sweep whatever is left on
the scheduled day. This base captures that skeleton once (DRY); concrete
strategies only implement :meth:`_signal`, the single line that makes them
different.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING

from dcatoolbox.broker.orders import Order
from dcatoolbox.config.enums import OrderSide
from dcatoolbox.strategies.base import Strategy

if TYPE_CHECKING:
    from dcatoolbox.backtesting.context import MarketContext

__all__ = ["BudgetDeploymentStrategy", "Signal"]

#: A triggered signal: ``(fired, execution_price_field)``.
Signal = tuple[bool, str]

_MIN_NOTIONAL = 1.0


class BudgetDeploymentStrategy(Strategy):
    """Deploy a fraction of remaining budget on a signal; sweep on the due day."""

    name = "abstract"

    #: Budget deployment policies.
    POLICIES = ("reset", "accumulate")

    def _validate(self) -> None:
        self.allocation: float = float(self.params.get("allocation", 0.25))
        if not 0.0 < self.allocation <= 1.0:
            raise ValueError("allocation must be in (0, 1]")
        self.budget_policy: str = str(self.params.get("budget_policy", "reset"))
        if self.budget_policy not in self.POLICIES:
            raise ValueError(f"budget_policy must be one of {self.POLICIES}")
        self._configure()

    def _configure(self) -> None:
        """Subclass hook to read and validate extra parameters."""

    @abstractmethod
    def _signal(self, context: MarketContext) -> Signal:
        """Return whether to buy now and which price field to execute against."""
        raise NotImplementedError

    def on_bar(self, context: MarketContext) -> list[Order]:
        """Deploy on signal; sweep the remainder on the due day (policy-aware).

        With ``budget_policy="reset"`` (default) any cash left on the scheduled
        day is fully invested, so each month's budget is always deployed. With
        ``budget_policy="accumulate"`` no sweep happens: unspent cash carries over
        to hunt for larger, less frequent dips (a true "buy the dip" mandate).
        """
        cash = context.available_cash
        if cash <= _MIN_NOTIONAL:
            return []
        if context.is_scheduled_day and self.budget_policy == "reset":
            return [self._buy(context, cash, "open", "scheduled")]
        fired, price_field = self._signal(context)
        if fired:
            notional = min(self.allocation * cash, cash)
            if notional >= _MIN_NOTIONAL:
                return [self._buy(context, notional, price_field, "dip")]
        return []

    def _buy(self, context: MarketContext, notional: float, price_field: str, reason: str) -> Order:
        """Construct a buy order for ``notional`` cash on the primary ticker."""
        return Order(
            ticker=context.primary_ticker,
            side=OrderSide.BUY,
            notional=notional,
            price_field=price_field,
            reason=reason,
        )
