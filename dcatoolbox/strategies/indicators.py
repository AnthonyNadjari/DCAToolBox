"""Vectorised technical indicators reused across strategies.

Keeping indicators here (rather than inlined in each strategy) avoids duplication
and gives every future strategy a tested, shared toolbox.
"""

from __future__ import annotations

import pandas as pd

__all__ = ["sma", "rsi"]


def sma(series: pd.Series, window: int) -> pd.Series:
    """Simple moving average over ``window`` observations."""
    return series.rolling(window=window, min_periods=window).mean()


def rsi(series: pd.Series, window: int = 14) -> pd.Series:
    """Wilder's Relative Strength Index of ``series`` over ``window`` periods.

    Returns values in ``[0, 100]``; the leading ``window`` entries are ``NaN``.
    """
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / window, min_periods=window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / window, min_periods=window, adjust=False).mean()
    # When average loss is 0 the ratio is +inf, which maps cleanly to an RSI of 100.
    rs = avg_gain / avg_loss
    return (100.0 - 100.0 / (1.0 + rs)).astype(float)
