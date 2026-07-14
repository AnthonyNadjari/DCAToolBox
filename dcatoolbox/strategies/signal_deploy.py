"""Signal-gated deployment: keep dry powder, deploy it on fear signals.

Implements the "buy the fear" thesis on a single asset: part of each month's
budget (``1 - base_deploy``) is held back as a reserve, which deploys entirely
when a chosen market-stress signal fires — high VIX, realized-vol spikes,
capitulation volume, or drawdowns — with a hard time-stop (``max_hold`` bars)
so the reserve can never rot indefinitely in cash.

The signal asset (e.g. ``^VIX``) rides along in the market data as a
non-tradable series; only the primary ticker is ever bought. Every signal is
computed on data up to the PREVIOUS close (orders fill at the current open),
matching the repo's look-ahead convention.

This strategy exists to give the "volumes / volatility / VIX can beat DCA even
on the S&P alone" hypothesis its fairest possible shot under the same audited
harness as everything else.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from dcatoolbox.broker.orders import Order
from dcatoolbox.config.enums import OrderSide
from dcatoolbox.strategies.base import Strategy
from dcatoolbox.strategies.registry import register_strategy

if TYPE_CHECKING:
    from dcatoolbox.backtesting.context import MarketContext

__all__ = ["SignalDeployStrategy"]

_MIN_NOTIONAL = 1.0
_SIGNALS = ("vix_pctl", "vix_abs", "rvol_pctl", "volume_cap", "drawdown")


@register_strategy
class SignalDeployStrategy(Strategy):
    """Reserve-and-release deployment gated by a stress signal.

    Parameters (via ``params``):
        signal: One of ``vix_pctl`` (VIX above trailing percentile),
            ``vix_abs`` (VIX above an absolute level), ``rvol_pctl``
            (21-day realized vol above trailing percentile), ``volume_cap``
            (volume spike + down day: capitulation), ``drawdown`` (price below
            its trailing 252-day high by a threshold).
        threshold: Signal threshold. Percentile signals: 0-1 (e.g. ``0.8``).
            ``vix_abs``: VIX points (e.g. ``30``). ``volume_cap``: volume
            multiple of its 63-day average (e.g. ``2.0``). ``drawdown``:
            depth (e.g. ``0.10``).
        base_deploy: Fraction of newly available cash invested immediately,
            unconditionally. The rest waits for the signal. Default ``0.0``.
        max_hold: Bars after which the reserve force-deploys anyway (bounded
            regret; nothing rots in cash forever). Default ``63``.
        pctl_window: Trailing window (bars) for percentile signals.
            Default ``1260`` (~5 years).
        signal_ticker: Series carrying the signal for VIX modes.
            Default ``"^VIX"``.
    """

    name = "signal_deploy"

    def _validate(self) -> None:
        self.signal = str(self.params.get("signal", "vix_pctl"))
        if self.signal not in _SIGNALS:
            raise ValueError(f"signal must be one of {_SIGNALS}")
        self.threshold = float(self.params.get("threshold", 0.8))
        self.base_deploy = float(self.params.get("base_deploy", 0.0))
        if not 0.0 <= self.base_deploy <= 1.0:
            raise ValueError("base_deploy must be in [0, 1]")
        self.max_hold = int(self.params.get("max_hold", 63))
        if self.max_hold < 1:
            raise ValueError("max_hold must be >= 1")
        self.pctl_window = int(self.params.get("pctl_window", 1260))
        self.signal_ticker = str(self.params.get("signal_ticker", "^VIX"))
        self._waiting = 0  # bars the current reserve has been waiting
        self._last_cash = 0.0  # expected post-trade cash, to detect new deposits

    def reset(self) -> None:
        """Clear run state between independent backtests."""
        self._waiting = 0
        self._last_cash = 0.0

    # -------------------------------- signal ---------------------------------
    def _fired(self, context: MarketContext) -> bool:
        """Evaluate the stress signal on data up to the previous close."""
        spy = context.histories[context.primary_ticker]
        close = spy["close"].to_numpy(dtype=float)[:-1]
        if len(close) < 30:
            return False

        if self.signal in ("vix_pctl", "vix_abs"):
            if self.signal_ticker not in context.histories:
                return False
            vix = context.histories[self.signal_ticker]["close"].to_numpy(dtype=float)[:-1]
            vix = vix[np.isfinite(vix)]
            if len(vix) < 30:
                return False
            if self.signal == "vix_abs":
                return float(vix[-1]) >= self.threshold
            window = vix[-self.pctl_window :]
            rank = float(np.mean(window <= vix[-1]))
            return rank >= self.threshold

        if self.signal == "rvol_pctl":
            tail = close[-(self.pctl_window + 22) :]
            rets = np.diff(tail) / tail[:-1]
            if len(rets) < 63:
                return False
            windows = np.lib.stride_tricks.sliding_window_view(rets, 21)
            rv = windows.std(axis=1, ddof=1)
            window = rv[-self.pctl_window :]
            return float(np.mean(window <= rv[-1])) >= self.threshold

        if self.signal == "volume_cap":
            vol = spy["volume"].to_numpy(dtype=float)[:-1]
            if len(vol) < 64 or not np.isfinite(vol[-64:]).all():
                return False
            avg = float(np.mean(vol[-64:-1]))
            day_ret = close[-1] / close[-2] - 1.0 if close[-2] > 0 else 0.0
            return avg > 0 and vol[-1] >= self.threshold * avg and day_ret < -0.01

        # drawdown
        window = close[-252:]
        peak = float(np.max(window))
        return peak > 0 and window[-1] <= peak * (1.0 - self.threshold)

    # -------------------------------- trading --------------------------------
    def on_bar(self, context: MarketContext) -> list[Order]:
        """Deploy the base tranche of new deposits; release the reserve on signal/time-stop."""
        cash = context.available_cash
        if cash <= _MIN_NOTIONAL:
            self._last_cash = max(cash, 0.0)
            self._waiting = 0
            return []

        orders: list[Order] = []
        committed = 0.0
        inflow = cash - self._last_cash
        if inflow > _MIN_NOTIONAL and self.base_deploy > 0:
            base = min(inflow * self.base_deploy, cash)
            if base > _MIN_NOTIONAL:
                orders.append(self._buy(context.primary_ticker, base, "base"))
                committed += base

        if cash - committed > _MIN_NOTIONAL:
            self._waiting += 1
            if self._fired(context) or self._waiting >= self.max_hold:
                orders.append(self._buy(context.primary_ticker, float("inf"), "signal"))
                committed = cash
                self._waiting = 0
        else:
            self._waiting = 0
        self._last_cash = cash - committed
        return orders

    @staticmethod
    def _buy(ticker: str, notional: float, reason: str) -> Order:
        """Build a buy order (the engine caps notional to available cash)."""
        return Order(
            ticker=ticker,
            side=OrderSide.BUY,
            notional=notional,
            price_field="open",
            reason=reason,
        )
