"""MonthlyDCA: the absolute benchmark strategy.

Every month, on the scheduled day, 100% of the available monthly budget is
invested in a single purchase. There are no other trades. Every other strategy in
the framework is measured against this one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dcatoolbox.broker.orders import Order
from dcatoolbox.config.enums import OrderSide
from dcatoolbox.strategies.base import Strategy
from dcatoolbox.strategies.registry import register_strategy

if TYPE_CHECKING:
    from dcatoolbox.backtesting.context import MarketContext

__all__ = ["MonthlyDCA"]

_MIN_NOTIONAL = 1e-6


@register_strategy
class MonthlyDCA(Strategy):
    """Invest the full monthly budget on the scheduled day, nothing else."""

    name = "monthly_dca"

    def _validate(self) -> None:
        self._price_field: str = self.params.get("price_field", "open")

    def on_bar(self, context: MarketContext) -> list[Order]:
        """Buy with all available cash on the scheduled day; otherwise idle."""
        if not context.is_scheduled_day:
            return []
        cash = context.available_cash
        if cash <= _MIN_NOTIONAL:
            return []
        return [
            Order(
                ticker=context.primary_ticker,
                side=OrderSide.BUY,
                notional=cash,
                price_field=self._price_field,
                reason="scheduled",
            )
        ]
