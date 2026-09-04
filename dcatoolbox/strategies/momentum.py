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
    """Trailing return over ``lookback`` bars ending at the PREVIOUS close.

    Momentum strategies fill at the current bar's OPEN, so the signal may only
    use information available before that open — i.e. up to the previous
    session's close. Using the current close would be a same-bar look-ahead
    (the fill price would predate the signal), which systematically inflates
    backtests.

    A ticker without enough (positive) history -- e.g. one that joins the basket
    after the primary, leaving NaN-padded bars -- is excluded rather than ranked
    on a NaN, which keeps the result identical to the in-browser JS engine.
    """
    if len(close) <= lookback + 1:
        return None
    current = close.iloc[-2]
    prior = close.iloc[-lookback - 2]
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
        rotate: If ``True``, the WHOLE portfolio follows the signal: holdings in
            anything but the current leader are sold on the scheduled day (and
            everything is liquidated to cash when the dual-momentum guard fires),
            classic Antonacci-style dual momentum. If ``False`` (default), only
            new contributions are routed to the leader and nothing is ever sold.
    """

    name = "momentum_rotation"

    def _validate(self) -> None:
        self.lookback = int(self.params.get("lookback", 126))
        self.absolute = bool(self.params.get("absolute", True))
        self.basket = self.params.get("basket")
        self.rotate = bool(self.params.get("rotate", False))

    def on_bar(self, context: MarketContext) -> list[Order]:
        """On the scheduled day, point the budget (and holdings if rotating) at the leader."""
        if not context.is_scheduled_day:
            return []
        cash = context.available_cash
        basket = self.basket or list(context.histories)
        ranked = [
            (t, _trailing_return(context.histories[t]["close"], self.lookback)) for t in basket
        ]
        ranked = [(t, r) for t, r in ranked if r is not None]
        if not ranked:  # warm-up: behave like DCA
            return [self._buy(context.primary_ticker, cash)] if cash > _MIN_NOTIONAL else []
        best_ticker, best_return = max(ranked, key=lambda x: x[1])
        if self.absolute and best_return <= 0:
            # Dual momentum: everything falling. Liquidate when rotating, else just wait.
            return self._sells(context, keep=None) if self.rotate else []
        orders = self._sells(context, keep=best_ticker) if self.rotate else []
        # The buy is capped to available cash AT EXECUTION TIME by the engine, so
        # after the sells settle it deploys cash + proceeds in one order.
        if cash > _MIN_NOTIONAL or orders:
            orders.append(self._buy(best_ticker, float("inf")))
        return orders

    @staticmethod
    def _sells(context: MarketContext, keep: str | None) -> list[Order]:
        """Sell every open position except ``keep`` (all of them when ``None``)."""
        return [
            Order(
                ticker=ticker,
                side=OrderSide.SELL,
                quantity=pos.quantity,
                price_field="open",
                reason="rotate",
            )
            for ticker, pos in context.portfolio.positions.items()
            if ticker != keep and pos.quantity > 1e-9
        ]

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
