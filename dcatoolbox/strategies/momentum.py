"""Momentum strategies: absolute (single-asset) and cross-sectional (multi-asset).

* :class:`AbsoluteMomentumStrategy` deploys the monthly budget only when the
  asset's trailing return is positive (otherwise it waits in cash) -- a simple
  bear-market filter.
* :class:`MomentumRotationStrategy` invests each month's budget into the
  best-performing instrument of a basket (cross-sectional / relative momentum),
  exploiting the engine's native multi-asset support.

Both are single self-registering modules; the engine is untouched.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dcatoolbox.broker.orders import Order
from dcatoolbox.config.enums import OrderSide
from dcatoolbox.strategies.base import Strategy
from dcatoolbox.strategies.registry import register_strategy

if TYPE_CHECKING:
    from dcatoolbox.backtesting.context import MarketContext

__all__ = ["AbsoluteMomentumStrategy", "MomentumRotationStrategy"]

_MIN_NOTIONAL = 1.0


def _trailing_return(close, lookback: int) -> float | None:
    """Return the trailing return over ``lookback`` bars, or ``None`` if undefined.

    A ticker without enough (positive) history -- e.g. one that joins the basket
    after the primary, leaving NaN-padded bars -- is excluded rather than ranked
    on a NaN, which keeps the result identical to the in-browser JS engine.
    """
    if len(close) <= lookback:
        return None
    current = close.iloc[-1]
    prior = close.iloc[-lookback - 1]
    if not (current > 0) or not (prior > 0):  # also rejects NaN
        return None
    return float(current / prior - 1.0)


@register_strategy
class AbsoluteMomentumStrategy(Strategy):
    """Invest the monthly budget only when trailing momentum is positive.

    Parameters (via ``params``):
        lookback: Momentum look-back in bars. Default ``126`` (~6 months).
    """

    name = "absolute_momentum"

    def _validate(self) -> None:
        self.lookback = int(self.params.get("lookback", 126))
        if self.lookback < 2:
            raise ValueError("lookback must be >= 2")

    def on_bar(self, context: MarketContext) -> list[Order]:
        """On the scheduled day, deploy only if trailing return > 0."""
        cash = context.available_cash
        if not context.is_scheduled_day or cash <= _MIN_NOTIONAL:
            return []
        trailing = _trailing_return(context.history["close"], self.lookback)
        if trailing is not None and trailing <= 0:
            return []  # negative momentum: hold cash
        return [
            Order(
                ticker=context.primary_ticker,
                side=OrderSide.BUY,
                notional=cash,
                price_field="open",
                reason="momentum",
            )
        ]


@register_strategy
class MomentumRotationStrategy(Strategy):
    """Invest each month into the basket's strongest instrument (relative momentum).

    Parameters (via ``params``):
        lookback: Momentum look-back in bars. Default ``126``.
        absolute: If ``True``, hold cash when the winner's momentum is negative.
            Default ``True`` (dual momentum).
        basket: Optional explicit list of tickers; defaults to all instruments
            available in the market context.
    """

    name = "momentum_rotation"

    def _validate(self) -> None:
        self.lookback = int(self.params.get("lookback", 126))
        self.absolute = bool(self.params.get("absolute", True))
        self.basket = self.params.get("basket")

    def on_bar(self, context: MarketContext) -> list[Order]:
        """On the scheduled day, buy the basket's best-momentum instrument."""
        cash = context.available_cash
        if not context.is_scheduled_day or cash <= _MIN_NOTIONAL:
            return []
        basket = self.basket or list(context.histories)
        ranked = [
            (t, _trailing_return(context.histories[t]["close"], self.lookback)) for t in basket
        ]
        ranked = [(t, r) for t, r in ranked if r is not None]
        if not ranked:
            return [self._buy(context.primary_ticker, cash)]  # warm-up: behave like DCA
        best_ticker, best_return = max(ranked, key=lambda x: x[1])
        if self.absolute and best_return <= 0:
            return []  # dual-momentum: all assets falling -> stay in cash
        return [self._buy(best_ticker, cash)]

    @staticmethod
    def _buy(ticker: str, cash: float) -> Order:
        """Build a full-cash buy order for ``ticker``."""
        return Order(
            ticker=ticker,
            side=OrderSide.BUY,
            notional=cash,
            price_field="open",
            reason="momentum",
        )
