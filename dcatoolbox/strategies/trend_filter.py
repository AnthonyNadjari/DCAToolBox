"""TrendFilterStrategy: a regime filter on top of DCA.

Invest the monthly budget only while the price is above its moving average (an
uptrend); otherwise hold the cash and deploy it once the trend resumes. The goal
is to avoid pouring money into sustained downtrends and thereby cut drawdowns.

Like every strategy it is a single self-registering module; the engine is
untouched.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dcatoolbox.broker.orders import Order
from dcatoolbox.config.enums import OrderSide
from dcatoolbox.strategies.base import Strategy
from dcatoolbox.strategies.indicators import sma
from dcatoolbox.strategies.registry import register_strategy

if TYPE_CHECKING:
    from dcatoolbox.backtesting.context import MarketContext

__all__ = ["TrendFilterStrategy"]

_MIN_NOTIONAL = 1.0


@register_strategy
class TrendFilterStrategy(Strategy):
    """Deploy the monthly budget only when price is above its moving average.

    Parameters (via ``params``):
        ma_window: Moving-average look-back in bars. Default ``200``.
    """

    name = "trend_filter"

    def _validate(self) -> None:
        self.ma_window = int(self.params.get("ma_window", 200))
        if self.ma_window < 2:
            raise ValueError("ma_window must be >= 2")

    def on_bar(self, context: MarketContext) -> list[Order]:
        """On the scheduled day, invest only if price is above its MA."""
        cash = context.available_cash
        if not context.is_scheduled_day or cash <= _MIN_NOTIONAL:
            return []
        # The order fills at the current bar's OPEN, so the trend test may only
        # use the previous close (same-bar close would be a look-ahead).
        close = context.history["close"].iloc[:-1]
        above = len(close) < self.ma_window or close.iloc[-1] > sma(close, self.ma_window).iloc[-1]
        if not above:
            return []  # downtrend: hold cash, deploy when the trend resumes
        return [
            Order(
                ticker=context.primary_ticker,
                side=OrderSide.BUY,
                notional=cash,
                price_field="open",
                reason="trend",
            )
        ]
