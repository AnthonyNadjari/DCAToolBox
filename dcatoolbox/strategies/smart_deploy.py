"""Smart deployment: data-driven target weights + free-frequency cash pacing.

A generalisation of rotation strategies for the real problem: money arrives
monthly, but NOTHING forces it to be deployed monthly, all at once, or into a
single asset. Each day this strategy:

1. Computes **target weights** over the basket (and implicitly cash) from
   lagged data only — several schemes:

   * ``winner``  — 100% on the best blended momentum (the old rotation);
   * ``softmax`` — weights proportional to ``exp(k * momentum)``: a smooth mix
     tilted toward the leader instead of all-or-nothing;
   * ``inv_vol`` — risk parity: weights proportional to inverse realised vol;
   * ``equal``   — fixed 1/N (a pacing-only control).

   Optional overlays: a per-asset **trend gate** (weight forced to 0 while the
   asset sits below its own 200-day average), the **dual-momentum guard**
   (everything negative -> target 100% cash) and a **volatility target** (the
   equity fraction scales like ``vol_target / realised_vol``, so the portfolio
   de-risks itself in storms without ever selling).

2. **Paces the deployment**: only ``deploy_rate`` of the available cash may be
   invested per day (1.0 = everything as soon as it is available). An optional
   **dip accelerator** multiplies the day's budget when the target asset trades
   below its recent high — buy weakness faster, in a controlled way.

3. Buys the most underweight asset (vs target) with the day's investable cash.
   Never sells: weights converge to target through the flows alone.

Signals use only closes up to the PREVIOUS session (orders fill at the current
open), so look-ahead is structurally impossible.
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

__all__ = ["SmartDeployStrategy"]

_MIN_NOTIONAL = 1.0
_SCHEMES = ("winner", "softmax", "inv_vol", "equal")


def _mom(c: np.ndarray, horizons: list[int]) -> float | None:
    """Equal-weight blended momentum from a lagged close array (or None)."""
    vals = []
    for h in horizons:
        if len(c) <= h:
            continue
        a, b = c[-1], c[-h - 1]
        if a > 0 and b > 0:
            vals.append(a / b - 1.0)
    return float(np.mean(vals)) if vals else None


@register_strategy
class SmartDeployStrategy(Strategy):
    """Target-weight accumulation with paced, data-driven cash deployment.

    Parameters (via ``params``):
        basket: Tickers to allocate across (default: all available).
        scheme: ``winner`` | ``softmax`` | ``inv_vol`` | ``equal``. Default
            ``softmax``.
        softmax_k: Sharpness of the softmax tilt. Default ``15``.
        horizons: Momentum horizons (bars) for the blended score. Default
            ``[63, 126, 252]``.
        trend_gate: Zero the weight of any asset below its own ``gate_window``
            moving average. Default ``False``.
        gate_window: Trend-gate MA window. Default ``200``.
        guard: All momentum scores <= 0 -> hold cash (dual momentum guard).
            Default ``True``.
        vol_target: Annualised vol target; equity fraction is
            ``min(1, vol_target / realised_vol)``. ``0`` disables. Default ``0``.
        vol_window: Realised-vol window in bars. Default ``63``.
        deploy_rate: Fraction of available cash deployable per day (1.0 = all
            at once). Default ``1.0``.
        dip_accel: Multiplier on the day's deployable cash when the buy target
            trades below ``(1 - dip_threshold)`` of its ``dip_window`` high.
            ``0``/``1`` disables. Default ``0``.
        dip_threshold: Dip depth that triggers the accelerator. Default ``0.05``.
        dip_window: High-water window for the dip test. Default ``20``.
    """

    name = "smart_deploy"

    def _validate(self) -> None:
        self.basket = self.params.get("basket")
        self.scheme = str(self.params.get("scheme", "softmax"))
        if self.scheme not in _SCHEMES:
            raise ValueError(f"scheme must be one of {_SCHEMES}")
        self.softmax_k = float(self.params.get("softmax_k", 15.0))
        self.horizons = [int(h) for h in self.params.get("horizons", [63, 126, 252])]
        self.trend_gate = bool(self.params.get("trend_gate", False))
        self.gate_window = int(self.params.get("gate_window", 200))
        self.guard = bool(self.params.get("guard", True))
        self.vol_target = float(self.params.get("vol_target", 0.0))
        self.vol_window = int(self.params.get("vol_window", 63))
        self.deploy_rate = float(self.params.get("deploy_rate", 1.0))
        if not 0.0 < self.deploy_rate <= 1.0:
            raise ValueError("deploy_rate must be in (0, 1]")
        self.dip_accel = float(self.params.get("dip_accel", 0.0))
        self.dip_threshold = float(self.params.get("dip_threshold", 0.05))
        self.dip_window = int(self.params.get("dip_window", 20))

    # ------------------------------- signals ---------------------------------
    def _weights(self, closes: dict[str, np.ndarray]) -> dict[str, float]:
        """Target weights per asset (sum <= 1; the remainder is cash)."""
        scores = {t: _mom(c, self.horizons) for t, c in closes.items()}
        scores = {t: s for t, s in scores.items() if s is not None}
        if not scores:
            return {}
        if self.guard and max(scores.values()) <= 0.0:
            return dict.fromkeys(scores, 0.0)  # everything falling: hold cash

        gated = dict(scores)
        if self.trend_gate:
            for t, c in closes.items():
                below = len(c) >= self.gate_window and c[-1] < float(
                    np.mean(c[-self.gate_window :])
                )
                if t in gated and below:
                    gated[t] = None  # below its own long MA: excluded
            gated = {t: s for t, s in gated.items() if s is not None}
            if not gated:
                return dict.fromkeys(scores, 0.0)

        if self.scheme == "winner":
            best = max(gated, key=lambda t: gated[t])
            w = {t: (1.0 if t == best else 0.0) for t in gated}
        elif self.scheme == "softmax":
            exps = {t: float(np.exp(self.softmax_k * s)) for t, s in gated.items()}
            total = sum(exps.values())
            w = {t: e / total for t, e in exps.items()}
        elif self.scheme == "inv_vol":
            iv = {}
            for t in gated:
                c = closes[t]
                if len(c) > self.vol_window + 1:
                    rets = np.diff(c[-self.vol_window - 1 :]) / c[-self.vol_window - 1 : -1]
                    vol = float(np.std(rets, ddof=1))
                    iv[t] = 1.0 / vol if vol > 1e-9 else 0.0
            total = sum(iv.values())
            w = (
                {t: v / total for t, v in iv.items()}
                if total > 0
                else dict.fromkeys(gated, 1.0 / len(gated))
            )
        else:  # equal
            w = dict.fromkeys(gated, 1.0 / len(gated))

        if self.vol_target > 0:
            # De-risk by scaling the whole equity sleeve, never by selling.
            port_vol = self._portfolio_vol(closes, w)
            if port_vol is not None and port_vol > 1e-9:
                scale = min(1.0, self.vol_target / port_vol)
                w = {t: x * scale for t, x in w.items()}
        return w

    def _portfolio_vol(self, closes: dict[str, np.ndarray], w: dict[str, float]) -> float | None:
        """Annualised realised vol of the weighted basket (lagged data)."""
        n = self.vol_window + 1
        series = []
        weights = []
        for t, x in w.items():
            c = closes[t]
            if x > 0 and len(c) >= n:
                series.append(np.diff(c[-n:]) / c[-n:-1])
                weights.append(x)
        if not series:
            return None
        total = sum(weights)
        if total <= 0:
            return None
        rets = np.average(np.vstack(series), axis=0, weights=[x / total for x in weights])
        return float(np.std(rets, ddof=1) * np.sqrt(252.0))

    # ------------------------------- trading ---------------------------------
    def on_bar(self, context: MarketContext) -> list[Order]:
        """Deploy up to ``deploy_rate`` of cash toward the most underweight asset."""
        cash = context.available_cash
        if cash <= _MIN_NOTIONAL:
            return []
        basket = self.basket or list(context.histories)
        # Signals may only use data known before today's open: drop today's bar.
        closes = {
            t: context.histories[t]["close"].to_numpy(dtype=float)[:-1]
            for t in basket
            if t in context.histories
        }
        closes = {t: c[np.isfinite(c)] for t, c in closes.items()}
        closes = {t: c for t, c in closes.items() if len(c) > 1}
        weights = self._weights(closes)
        if not weights:  # warm-up: behave like plain DCA
            if context.is_scheduled_day:
                return [self._buy(context.primary_ticker, cash)]
            return []
        if max(weights.values()) <= 0.0:
            return []  # guard active: hold cash

        # Current sleeve values at the last known close.
        values = {}
        for t in weights:
            pos = context.portfolio.positions.get(t)
            values[t] = (pos.quantity if pos else 0.0) * closes[t][-1]
        equity = sum(values.values())
        total = equity + cash
        wsum = sum(weights.values())
        # Most underweight asset vs its target share of the TOTAL portfolio.
        target = max(weights, key=lambda t: weights[t] * total - values[t])
        gap = weights[target] * total - values[target]
        # Respect the vol-target cash sleeve: never push equity above wsum*total.
        max_equity_add = max(0.0, wsum * total - equity)

        investable = cash * self.deploy_rate
        if self.dip_accel > 1 and self._in_dip(closes[target]):
            investable *= self.dip_accel
        notional = min(investable, cash, max(gap, 0.0), max_equity_add)
        if notional <= _MIN_NOTIONAL:
            return []
        return [self._buy(target, notional)]

    def _in_dip(self, c: np.ndarray) -> bool:
        """Is the asset trading below (1 - dip_threshold) of its recent high?"""
        if len(c) < self.dip_window + 1:
            return False
        high = float(np.max(c[-self.dip_window :]))
        return high > 0 and c[-1] <= high * (1.0 - self.dip_threshold)

    @staticmethod
    def _buy(ticker: str, notional: float) -> Order:
        """Build a buy order (the engine caps notional to available cash)."""
        return Order(
            ticker=ticker,
            side=OrderSide.BUY,
            notional=notional,
            price_field="open",
            reason="deploy",
        )
