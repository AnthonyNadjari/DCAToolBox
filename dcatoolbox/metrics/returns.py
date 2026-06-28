"""Return- and cash-flow analytics shared by the metrics layer.

These helpers carefully separate *investment performance* from the distorting
effect of external contributions, which is essential for DCA portfolios whose
equity grows partly because new money is paid in.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import optimize

__all__ = [
    "external_flows",
    "time_weighted_returns",
    "wealth_index",
    "drawdown_series",
    "xirr",
]

_DAYS_PER_YEAR = 365.0


def external_flows(history: pd.DataFrame) -> pd.Series:
    """Per-bar external contributions, derived from cumulative invested capital."""
    invested = history["invested_capital"]
    if len(invested) == 0:
        return pd.Series(dtype=float)
    flows = invested.diff()
    flows.iloc[0] = invested.iloc[0]
    return flows.fillna(0.0)


def time_weighted_returns(history: pd.DataFrame) -> pd.Series:
    """Daily time-weighted returns, neutralising contribution effects.

    A contribution is assumed to arrive at the start of its bar, so the
    investment return for bar ``t`` is ``V[t] / (V[t-1] + flow[t]) - 1``.
    """
    if len(history) < 2:
        return pd.Series(dtype=float)
    equity = history["total_value"]
    flows = external_flows(history)
    prior = equity.shift(1) + flows
    returns = equity / prior - 1.0
    return returns.iloc[1:].replace([np.inf, -np.inf], np.nan).fillna(0.0)


def wealth_index(history: pd.DataFrame) -> pd.Series:
    """Growth of 1 unit under the time-weighted returns (for drawdown/risk)."""
    twr = time_weighted_returns(history)
    return (1.0 + twr).cumprod()


def drawdown_series(index: pd.Series) -> pd.Series:
    """Drawdown of a wealth/price series from its running maximum (<= 0)."""
    running_max = index.cummax()
    return index / running_max - 1.0


def xirr(amounts: list[float], dates: list[pd.Timestamp], *, guess: float = 0.1) -> float:
    """Annualised money-weighted return for dated cash flows (Newton + bisection).

    Args:
        amounts: Signed cash flows (negative = paid in, positive = received).
        dates: Matching timestamps for each cash flow.
        guess: Initial rate guess for the solver.

    Returns:
        The annual XIRR, or ``nan`` if it cannot be determined.
    """
    if len(amounts) < 2 or all(a >= 0 for a in amounts) or all(a <= 0 for a in amounts):
        return float("nan")
    t0 = min(dates)
    years = np.array([(d - t0).days / _DAYS_PER_YEAR for d in dates])
    cash = np.array(amounts, dtype=float)

    def npv(rate: float) -> float:
        return float(np.sum(cash / (1.0 + rate) ** years))

    # Prefer a deterministic bracketed solve so the result is independent of the
    # initial guess (and matches the JS engine's solver bit-for-bit).
    low, high = -0.9999, 10.0
    try:
        if npv(low) * npv(high) < 0:
            return float(optimize.brentq(npv, low, high, maxiter=200))
    except (ValueError, RuntimeError):  # pragma: no cover - solver fallback
        pass
    try:
        return float(optimize.newton(npv, guess, maxiter=100))
    except (RuntimeError, OverflowError, FloatingPointError):  # pragma: no cover
        return float("nan")
