"""Adaptive momentum: walk-forward-recalibrated, conviction-sized rotation.

This is the "ML-light" evolution of :class:`MomentumRotationStrategy`, built for
three demands plain monthly rotation cannot meet:

* **Act more often than monthly.** The signal is evaluated every
  ``check_every`` trading days (5 = weekly, 1 = daily), independent of the
  deposit calendar. Contributions still arrive monthly, but decisions do not
  wait for the 26th.
* **Recalibrate the model.** Instead of one fixed look-back, the score blends
  several momentum horizons. Every ``recalibrate_every`` bars the horizon
  weights are re-fitted on the trailing ``train_window`` bars only (predictive
  power of each horizon for forward returns), which makes the whole backtest a
  continuous walk-forward: every decision uses parameters fitted strictly on
  data available at the time.
* **Size by conviction.** A normal positive signal deploys one monthly tranche;
  a *negative* regime holds cash (which builds a reserve); a genuine
  opportunity — strong blended momentum above ``hi_threshold``, or the leader
  dipping ``dip_boost`` below its own one-year high while its long momentum is
  still positive — deploys the WHOLE reserve at once ("if the opportunity is
  real, invest more").

The strategy reads ``context.histories`` truncated by the engine at the current
bar and then drops the current bar itself before computing any signal: orders
fill at the current OPEN, so only information available before that open (the
previous close and older) may drive them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from dcatoolbox.broker.orders import Order
from dcatoolbox.config.enums import OrderSide
from dcatoolbox.strategies.base import Strategy
from dcatoolbox.strategies.registry import register_strategy

if TYPE_CHECKING:
    from dcatoolbox.backtesting.context import MarketContext

__all__ = ["AdaptiveMomentumStrategy"]

_MIN_NOTIONAL = 1.0
_FORWARD = 21  # bars ahead used to measure each horizon's predictive power


def _trailing(close: pd.Series, lookback: int) -> float | None:
    """Trailing return over ``lookback`` bars, or ``None`` when undefined."""
    if len(close) <= lookback:
        return None
    current, prior = close.iloc[-1], close.iloc[-lookback - 1]
    if not (current > 0) or not (prior > 0):  # also rejects NaN
        return None
    return float(current / prior - 1.0)


@register_strategy
class AdaptiveMomentumStrategy(Strategy):
    """Walk-forward multi-horizon momentum rotation with conviction sizing.

    Parameters (via ``params``):
        basket: Tickers to rotate across (default: every instrument available).
        check_every: Evaluate the signal every N bars. Default ``5`` (weekly).
        horizons: Candidate momentum horizons in bars. Default
            ``[21, 63, 126, 252]``.
        recalibrate_every: Re-fit horizon weights every N bars. Default ``21``.
        train_window: Trailing bars used to fit the weights. Default ``756``.
        hi_threshold: Blended leader momentum at/above which the whole cash
            reserve deploys. Default ``0.10``.
        lo_threshold: Blended leader momentum below which nothing is bought
            (cash accumulates). Default ``0.0`` (the dual-momentum guard).
        dip_boost: Leader drawdown from its 1-year high that counts as an
            opportunity (whole reserve deploys) while long momentum stays
            positive. Default ``0.15``. Set ``0`` to disable.
        rotate: If ``True`` the whole portfolio follows the leader (sell what
            is not the leader; liquidate on a negative regime). Default
            ``False`` (accumulation only).
    """

    name = "adaptive_momentum"

    def _validate(self) -> None:
        self.basket = self.params.get("basket")
        self.check_every = int(self.params.get("check_every", 5))
        self.horizons = [int(h) for h in self.params.get("horizons", [21, 63, 126, 252])]
        self.recalibrate_every = int(self.params.get("recalibrate_every", 21))
        self.train_window = int(self.params.get("train_window", 756))
        self.hi_threshold = float(self.params.get("hi_threshold", 0.10))
        self.lo_threshold = float(self.params.get("lo_threshold", 0.0))
        self.dip_boost = float(self.params.get("dip_boost", 0.15))
        self.rotate = bool(self.params.get("rotate", False))
        if self.check_every < 1:
            raise ValueError("check_every must be >= 1")
        if not self.horizons or min(self.horizons) < 2:
            raise ValueError("horizons must be >= 2 bars")
        if self.hi_threshold < self.lo_threshold:
            raise ValueError("hi_threshold must be >= lo_threshold")
        self._weights: np.ndarray = np.full(len(self.horizons), 1 / len(self.horizons))
        self._last_fit = -(10**9)

    def reset(self) -> None:
        """Clear fitted state between independent backtests."""
        self._weights = np.full(len(self.horizons), 1 / len(self.horizons))
        self._last_fit = -(10**9)

    # ------------------------------ calibration ------------------------------
    def _refit(self, closes: dict[str, pd.Series], bar: int) -> None:
        """Re-fit horizon weights on the trailing train window (walk-forward).

        Each horizon's weight is its (clipped-positive) information
        coefficient: the correlation, pooled across the basket, between the
        horizon's trailing momentum and the NEXT ``_FORWARD``-bar return —
        computed strictly inside the trailing window, so nothing the model
        sees postdates the current bar.
        """
        ics = np.zeros(len(self.horizons))
        for k, h in enumerate(self.horizons):
            xs: list[float] = []
            ys: list[float] = []
            for close in closes.values():
                c = close.to_numpy(dtype=float)[-self.train_window :]
                if len(c) < h + 2 * _FORWARD + 2:
                    continue
                # momentum at t (needs h bars back), forward return t -> t+21
                mom = c[h:-_FORWARD] / c[: -h - _FORWARD] - 1.0
                fwd = c[h + _FORWARD :] / c[h:-_FORWARD] - 1.0
                ok = np.isfinite(mom) & np.isfinite(fwd)
                xs.extend(mom[ok])
                ys.extend(fwd[ok])
            if len(xs) > 30 and np.std(xs) > 1e-12 and np.std(ys) > 1e-12:
                ics[k] = float(np.corrcoef(xs, ys)[0, 1])
        positive = np.clip(ics, 0.0, None)
        total = positive.sum()
        self._weights = (
            positive / total
            if total > 1e-9
            else np.full(len(self.horizons), 1 / len(self.horizons))
        )
        self._last_fit = bar

    def _score(self, close: pd.Series) -> float | None:
        """Blended multi-horizon momentum for one ticker (None = not rankable)."""
        parts = [_trailing(close, h) for h in self.horizons]
        if parts[0] is None and all(p is None for p in parts):
            return None
        # A ticker too young for a long horizon is scored on the horizons it has.
        vals = np.array([p if p is not None else np.nan for p in parts], dtype=float)
        mask = np.isfinite(vals)
        if not mask.any():
            return None
        w = self._weights[mask]
        if w.sum() <= 1e-12:
            w = np.full(mask.sum(), 1 / mask.sum())
        return float(np.dot(vals[mask], w / w.sum()))

    # -------------------------------- trading --------------------------------
    def on_bar(self, context: MarketContext) -> list[Order]:
        """Every ``check_every`` bars: rank, gate by regime, size by conviction."""
        bar = len(context.history) - 1
        if bar % self.check_every != 0:
            return []
        basket = self.basket or list(context.histories)
        # Orders fill at the CURRENT bar's open, so every signal below may only
        # use information available before that open: drop the current bar and
        # compute everything on data up to the previous close. (Using the
        # same-bar close would be a look-ahead that inflates the backtest.)
        closes = {
            t: context.histories[t]["close"].iloc[:-1] for t in basket if t in context.histories
        }
        if bar - self._last_fit >= self.recalibrate_every:
            self._refit(closes, bar)

        ranked = [(t, self._score(c)) for t, c in closes.items()]
        ranked = [(t, s) for t, s in ranked if s is not None]
        cash = context.available_cash
        if not ranked:  # warm-up: nothing rankable yet, behave like DCA
            if context.is_scheduled_day and cash > _MIN_NOTIONAL:
                return [self._buy(context.primary_ticker, cash)]
            return []
        leader, strength = max(ranked, key=lambda x: x[1])

        if strength < self.lo_threshold:
            # Negative regime: hold (and liquidate when rotating). Cash builds
            # the reserve that conviction deploys later.
            return self._sells(context, keep=None) if self.rotate else []

        orders = self._sells(context, keep=leader) if self.rotate else []
        opportunity = strength >= self.hi_threshold or self._is_dip(closes[leader])
        tranche = cash if opportunity else min(cash, context.monthly_budget)
        if tranche > _MIN_NOTIONAL or orders:
            orders.append(self._buy(leader, tranche if tranche > _MIN_NOTIONAL else float("inf")))
        return orders

    def _is_dip(self, close: pd.Series) -> bool:
        """Opportunity check: leader well below its 1-year high, uptrend intact."""
        if self.dip_boost <= 0 or len(close) < 253:
            return False
        window = close.iloc[-252:]
        peak = float(window.max())
        if not peak > 0:
            return False
        drawdown = float(window.iloc[-1]) / peak - 1.0
        year = _trailing(close, 252)
        return drawdown <= -self.dip_boost and year is not None and year > 0

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
    def _buy(ticker: str, notional: float) -> Order:
        """Build a buy order for ``ticker`` (engine caps notional to cash)."""
        return Order(
            ticker=ticker,
            side=OrderSide.BUY,
            notional=notional,
            price_field="open",
            reason="momentum",
        )
