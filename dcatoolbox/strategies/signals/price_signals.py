"""Concrete, interchangeable dip-detection signal generators."""

from __future__ import annotations

import pandas as pd

from dcatoolbox.strategies.signals.base import SignalGenerator

__all__ = [
    "OpenVsOpenSignal",
    "CloseVsCloseSignal",
    "OpenVsCloseSignal",
    "CloseVsOpenSignal",
    "DrawdownNDaysSignal",
    "CumulativeReturnSignal",
]


class OpenVsOpenSignal(SignalGenerator):
    """Today's open versus yesterday's open."""

    execution_price_field = "open"

    def compute(self, history: pd.DataFrame) -> float:
        """Return ``open[t] / open[t-1] - 1``."""
        if len(history) < 2:
            return 0.0
        return self._pct_change(history["open"].iloc[-1], history["open"].iloc[-2])


class CloseVsCloseSignal(SignalGenerator):
    """Today's close versus yesterday's close."""

    execution_price_field = "close"

    def compute(self, history: pd.DataFrame) -> float:
        """Return ``close[t] / close[t-1] - 1``."""
        if len(history) < 2:
            return 0.0
        return self._pct_change(history["close"].iloc[-1], history["close"].iloc[-2])


class OpenVsCloseSignal(SignalGenerator):
    """Today's open versus yesterday's close (overnight gap)."""

    execution_price_field = "open"

    def compute(self, history: pd.DataFrame) -> float:
        """Return ``open[t] / close[t-1] - 1``."""
        if len(history) < 2:
            return 0.0
        return self._pct_change(history["open"].iloc[-1], history["close"].iloc[-2])


class CloseVsOpenSignal(SignalGenerator):
    """Today's close versus today's open (intraday move)."""

    execution_price_field = "close"

    def compute(self, history: pd.DataFrame) -> float:
        """Return ``close[t] / open[t] - 1``."""
        if len(history) < 1:
            return 0.0
        return self._pct_change(history["close"].iloc[-1], history["open"].iloc[-1])


class DrawdownNDaysSignal(SignalGenerator):
    """Drawdown of the latest close from its rolling ``window``-day high."""

    execution_price_field = "close"

    def __init__(self, window: int = 20) -> None:
        """Initialise with the look-back ``window`` in bars."""
        if window < 1:
            raise ValueError("window must be >= 1")
        self.window = window

    def compute(self, history: pd.DataFrame) -> float:
        """Return ``close[t] / max(close[-window:]) - 1`` (<= 0)."""
        if len(history) < 2:
            return 0.0
        recent = history["close"].iloc[-self.window :]
        return self._pct_change(recent.iloc[-1], float(recent.max()))


class CumulativeReturnSignal(SignalGenerator):
    """Cumulative return of the close over the last ``window`` bars."""

    execution_price_field = "close"

    def __init__(self, window: int = 5) -> None:
        """Initialise with the look-back ``window`` in bars."""
        if window < 1:
            raise ValueError("window must be >= 1")
        self.window = window

    def compute(self, history: pd.DataFrame) -> float:
        """Return ``close[t] / close[t-window] - 1``."""
        if len(history) <= self.window:
            return 0.0
        return self._pct_change(history["close"].iloc[-1], history["close"].iloc[-self.window - 1])
