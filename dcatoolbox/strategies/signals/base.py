"""Abstract base class for dip-detection signal generators.

A signal generator turns the price history available *now* into a single scalar
"move" for the latest bar, expressed as a return where a **negative** value means
a decline. Strategies stay agnostic to *how* the move is measured: they only
compare it to a threshold. New detection methods plug in without touching any
strategy or the engine.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

__all__ = ["SignalGenerator"]


class SignalGenerator(ABC):
    """Compute the latest price move from historical OHLCV data."""

    #: Bar field a triggered order should execute against ("open" or "close").
    execution_price_field: str = "open"

    @abstractmethod
    def compute(self, history: pd.DataFrame) -> float:
        """Return the latest move as a signed return (negative = decline).

        Args:
            history: OHLCV frame up to and including the current bar. Must never
                contain future bars.

        Returns:
            The latest move; ``0.0`` when there is insufficient history.
        """
        raise NotImplementedError

    @staticmethod
    def _pct_change(numerator: float, denominator: float) -> float:
        """Safe percentage change, returning ``0.0`` for a non-positive base."""
        return (numerator / denominator - 1.0) if denominator > 0 else 0.0
